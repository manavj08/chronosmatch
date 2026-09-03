"""
database/tests/test_ledger.py
---------------------------------
Day 14: tests for database/ledger.py --- schema creation, save/read
functions, statistics, and the INSERT OR IGNORE duplicate-safety
behavior.
"""

import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from database import ledger

TEST_DB_PATH = str(Path(__file__).resolve().parent / "test_ledger_temp.db")


@pytest.fixture
def conn():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    connection = ledger.get_connection(TEST_DB_PATH)
    yield connection
    connection.close()
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)


def make_trade(trade_id, buy_id=1, sell_id=2, price=100.0, quantity=10):
    now = time.perf_counter_ns()
    return {
        "trade_id": trade_id, "buy_order_id": buy_id, "sell_order_id": sell_id,
        "price": price, "quantity": quantity,
        "entry_timestamp": now - 1000, "exit_timestamp": now, "latency_ns": 1000,
    }


def test_schema_created_on_connect(conn):
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
    assert cursor.fetchone() is not None


def test_save_and_retrieve_single_trade(conn):
    ledger.save_trade(conn, make_trade(1), flushed_at=123)
    conn.commit()

    trades = ledger.get_recent_trades(conn, limit=10)
    assert len(trades) == 1
    assert trades[0]["trade_id"] == 1


def test_save_trades_batch_inserts_all(conn):
    trades = [make_trade(i) for i in range(1, 11)]
    inserted = ledger.save_trades_batch(conn, trades, flushed_at=123)

    assert inserted == 10
    assert ledger.get_statistics(conn)["total_trades"] == 10


def test_duplicate_trade_id_is_ignored_not_duplicated():
    """INSERT OR IGNORE on the primary key --- flushing the same
    trade twice (e.g. a flusher restart) must not create a duplicate
    row or raise an error."""
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    conn = ledger.get_connection(TEST_DB_PATH)

    ledger.save_trade(conn, make_trade(1), flushed_at=100)
    conn.commit()
    ledger.save_trade(conn, make_trade(1), flushed_at=200)  # same trade_id again
    conn.commit()

    trades = ledger.get_recent_trades(conn, limit=10)
    assert len(trades) == 1

    conn.close()
    os.remove(TEST_DB_PATH)


def test_get_recent_trades_newest_first(conn):
    for i in range(1, 6):
        ledger.save_trade(conn, make_trade(i), flushed_at=i)
    conn.commit()

    recent = ledger.get_recent_trades(conn, limit=3)
    assert [t["trade_id"] for t in recent] == [5, 4, 3]


def test_get_trade_history_chronological_order(conn):
    for i in range(1, 6):
        ledger.save_trade(conn, make_trade(i), flushed_at=i)
    conn.commit()

    history = ledger.get_trade_history(conn, limit=10)
    assert [t["trade_id"] for t in history] == [1, 2, 3, 4, 5]


def test_get_trade_history_pagination(conn):
    for i in range(1, 11):
        ledger.save_trade(conn, make_trade(i), flushed_at=i)
    conn.commit()

    page1 = ledger.get_trade_history(conn, limit=5, offset=0)
    page2 = ledger.get_trade_history(conn, limit=5, offset=5)

    assert [t["trade_id"] for t in page1] == [1, 2, 3, 4, 5]
    assert [t["trade_id"] for t in page2] == [6, 7, 8, 9, 10]


def test_get_statistics_on_empty_ledger(conn):
    stats = ledger.get_statistics(conn)
    assert stats["total_trades"] == 0
    assert stats["total_volume"] == 0
    assert stats["average_price"] == 0


def test_get_statistics_aggregates_correctly(conn):
    ledger.save_trade(conn, make_trade(1, price=100.0, quantity=10), flushed_at=1)
    ledger.save_trade(conn, make_trade(2, price=200.0, quantity=20), flushed_at=2)
    conn.commit()

    stats = ledger.get_statistics(conn)
    assert stats["total_trades"] == 2
    assert stats["total_volume"] == 30
    assert stats["average_price"] == 150.0


def test_clear_database_removes_all_rows_keeps_schema(conn):
    ledger.save_trade(conn, make_trade(1), flushed_at=1)
    conn.commit()
    assert ledger.get_statistics(conn)["total_trades"] == 1

    ledger.clear_database(conn)

    assert ledger.get_statistics(conn)["total_trades"] == 0
    # Schema should still exist --- clear_database doesn't drop the table
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
    assert cursor.fetchone() is not None
