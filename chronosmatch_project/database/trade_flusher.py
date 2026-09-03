"""
database/trade_flusher.py
----------------------------
MEMBER B'S ASYNC FLUSH SERVICE (Day 14).

Per spec: "Write a background process that asynchronously flushes the
matched trades from the mmap buffer to a permanent SQLite/ClickHouse
ledger for auditing."

Design: an asyncio task that periodically calls
OrderBookCython.get_trades_since() to pull only NEW trades since its
last flush, then writes them to SQLite in one batched transaction.
Runs on an interval (default 100ms) rather than after every single
trade --- flushing after every trade would mean a disk write on the
matching engine's critical path (defeating the point of keeping
matching itself GC-free and fast); batching on an interval means the
engine keeps running at full speed and the ledger catches up
periodically, which is what "asynchronously" means here.

This does NOT read from the mmap ring buffer directly (despite the
spec phrase "flushes ... from the mmap buffer") --- it reads from the
engine's OWN trade history (get_trades_since()), which is the
authoritative record of completed trades. The mmap ring buffer only
ever holds INCOMING orders waiting to be matched; by the time a trade
exists at all, it's already been recorded by the engine, not sitting
in the ring buffer. This distinction is called out explicitly here so
the terminology doesn't create a false impression of a second,
separate data source.
"""

import asyncio
import time


class TradeFlusher:
    """
    start()/stop()/pause()/resume() match the shape used elsewhere in
    this project (simulator/market_firehose.py) for consistency.
    """

    def __init__(self, order_book, db_connection, flush_interval_seconds: float = 0.1):
        self.order_book = order_book
        self.db_connection = db_connection
        self.flush_interval_seconds = flush_interval_seconds

        self._running = False
        self._paused = False
        self._task: asyncio.Task | None = None
        self._last_flushed_index = 0

        # Stats, useful for the eventual dashboard and for tests.
        self.total_flushed = 0
        self.flush_cycles = 0
        self.last_flush_error: str | None = None

    async def _run(self):
        # Imported here, not at module level, so this module can be
        # imported without requiring database/ledger.py's sqlite3
        # dependency to already be wired up in every test context ---
        # keeps the import graph light for tests that only care about
        # the flusher's scheduling logic.
        from database import ledger

        while self._running:
            if self._paused:
                await asyncio.sleep(self.flush_interval_seconds)
                continue

            try:
                self._flush_once(ledger)
            except Exception as e:  # noqa: BLE001 --- deliberately broad:
                # a flush failure (e.g. disk full, db locked) must
                # never crash the flusher loop or, worse, the matching
                # engine it's attached to. Recorded for visibility,
                # loop continues and retries next cycle.
                self.last_flush_error = str(e)

            await asyncio.sleep(self.flush_interval_seconds)

    def _flush_once(self, ledger_module) -> int:
        """One flush cycle: pull new trades since the last flush,
        write them in a single batched transaction. Returns the
        number of trades flushed this cycle (0 if nothing new)."""
        new_trades = self.order_book.get_trades_since(self._last_flushed_index)
        if not new_trades:
            self.flush_cycles += 1
            return 0

        flushed_at = time.perf_counter_ns()
        inserted = ledger_module.save_trades_batch(self.db_connection, new_trades, flushed_at)

        self._last_flushed_index = self.order_book.trade_count
        self.total_flushed += inserted
        self.flush_cycles += 1
        return inserted

    def start(self):
        if self._running:
            return
        self._running = True
        self._paused = False
        self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        self._running = False
        if self._task is not None:
            await self._task
            self._task = None

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    async def flush_now(self):
        """Force an immediate flush outside the normal interval ---
        useful for tests and for a clean shutdown sequence (flush
        anything pending before the process exits, rather than
        waiting up to flush_interval_seconds and potentially losing
        the most recent trades if the process is killed first)."""
        from database import ledger
        return self._flush_once(ledger)

    def get_stats(self) -> dict:
        return {
            "total_flushed": self.total_flushed,
            "flush_cycles": self.flush_cycles,
            "last_flushed_index": self._last_flushed_index,
            "last_flush_error": self.last_flush_error,
        }
