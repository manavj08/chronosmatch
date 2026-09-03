"""
database/ledger.py
---------------------
MEMBER B'S TRADE LEDGER (Day 14).

Per spec: "Write a background process that asynchronously flushes the
matched trades from the mmap buffer to a permanent SQLite/ClickHouse
ledger for auditing."

This module owns the SQLite schema and connection. The actual async
flush loop lives in trade_flusher.py --- kept separate so the schema/
storage concern and the "when and how often to flush" concern don't
get tangled together.

Design choices:
- SQLite, not ClickHouse: simple, no separate server process to run,
  more than adequate for demonstrating a correct audit trail at this
  project's scale. ClickHouse would be the natural upgrade for a real
  production HFT system's write volume, but adds real operational
  complexity (a server to deploy and manage) this project doesn't
  need to take on to prove the concept. Noted honestly, not silently
  decided.
- One row per trade, storing everything the engine already computed
  (including Day 12's entry/exit timestamps and latency_ns) --- the
  ledger is meant to be a durable, queryable record of exactly what
  the in-memory engine produced, not a separate/simplified view of it.
"""

import os
import sqlite3

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chronosmatch_ledger.db"
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    trade_id        INTEGER PRIMARY KEY,
    buy_order_id    INTEGER NOT NULL,
    sell_order_id   INTEGER NOT NULL,
    price           REAL NOT NULL,
    quantity        INTEGER NOT NULL,
    entry_timestamp INTEGER NOT NULL,
    exit_timestamp  INTEGER NOT NULL,
    latency_ns      INTEGER NOT NULL,
    flushed_at      INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_trades_exit_timestamp ON trades(exit_timestamp);
"""


def get_connection(db_path: str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Opens (creating if needed) the ledger database and ensures the
    schema exists. Safe to call repeatedly --- CREATE TABLE/INDEX IF
    NOT EXISTS, no error on a second call against an existing db."""
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def save_trade(conn: sqlite3.Connection, trade: dict, flushed_at: int) -> None:
    """Insert one trade dict (same shape as OrderBookCython.trades /
    get_trades_since()) into the ledger. Uses INSERT OR IGNORE on
    trade_id as the primary key --- if the same trade is ever flushed
    twice (e.g. a flusher restart re-reading from a stale position),
    this is a safe no-op rather than a duplicate row or a crash."""
    conn.execute(
        """
        INSERT OR IGNORE INTO trades
            (trade_id, buy_order_id, sell_order_id, price, quantity,
             entry_timestamp, exit_timestamp, latency_ns, flushed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            trade["trade_id"], trade["buy_order_id"], trade["sell_order_id"],
            trade["price"], trade["quantity"], trade["entry_timestamp"],
            trade["exit_timestamp"], trade["latency_ns"], flushed_at,
        ),
    )


def save_trades_batch(conn: sqlite3.Connection, trades: list, flushed_at: int) -> int:
    """Insert several trades in one transaction --- much faster than
    committing after every single row when a flush cycle picks up a
    batch of new trades at once. Returns the number of rows actually
    inserted (excludes any that were already present via INSERT OR
    IGNORE)."""
    if not trades:
        return 0
    cursor = conn.executemany(
        """
        INSERT OR IGNORE INTO trades
            (trade_id, buy_order_id, sell_order_id, price, quantity,
             entry_timestamp, exit_timestamp, latency_ns, flushed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                t["trade_id"], t["buy_order_id"], t["sell_order_id"],
                t["price"], t["quantity"], t["entry_timestamp"],
                t["exit_timestamp"], t["latency_ns"], flushed_at,
            )
            for t in trades
        ],
    )
    conn.commit()
    return cursor.rowcount


def get_recent_trades(conn: sqlite3.Connection, limit: int = 50) -> list:
    """Most recent trades, newest first."""
    cursor = conn.execute(
        "SELECT * FROM trades ORDER BY trade_id DESC LIMIT ?", (limit,)
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_trade_history(conn: sqlite3.Connection, limit: int = 1000, offset: int = 0) -> list:
    """Trades in chronological order, paginated."""
    cursor = conn.execute(
        "SELECT * FROM trades ORDER BY trade_id ASC LIMIT ? OFFSET ?", (limit, offset)
    )
    columns = [d[0] for d in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def get_statistics(conn: sqlite3.Connection) -> dict:
    """Aggregate stats over everything currently in the ledger."""
    cursor = conn.execute(
        """
        SELECT
            COUNT(*) as total_trades,
            COALESCE(SUM(quantity), 0) as total_volume,
            COALESCE(AVG(price), 0) as average_price,
            COALESCE(AVG(latency_ns), 0) as average_latency_ns,
            COALESCE(MAX(latency_ns), 0) as max_latency_ns
        FROM trades
        """
    )
    row = cursor.fetchone()
    return {
        "total_trades": row[0],
        "total_volume": row[1],
        "average_price": row[2],
        "average_latency_ns": row[3],
        "max_latency_ns": row[4],
    }


def clear_database(conn: sqlite3.Connection) -> None:
    """Deletes all rows --- kept for test isolation and manual demo
    resets. Does not drop the table/schema."""
    conn.execute("DELETE FROM trades")
    conn.commit()
