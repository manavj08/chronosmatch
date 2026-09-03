"""
database/tests/test_trade_flusher.py
-----------------------------------------
Day 14: tests for database/trade_flusher.py --- the async background
flush service connecting the matching engine's trade history to the
SQLite ledger.
"""

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "matching_engine"))

try:
    from order_book import OrderBookCython
except ImportError:
    pytest.skip(
        "Cython extension not built. Run: python setup_demo.py",
        allow_module_level=True,
    )

from database import ledger
from database.trade_flusher import TradeFlusher

TEST_DB_PATH = str(Path(__file__).resolve().parent / "test_flusher_temp.db")


def fresh_db():
    if os.path.exists(TEST_DB_PATH):
        os.remove(TEST_DB_PATH)
    return ledger.get_connection(TEST_DB_PATH)


def make_book_with_resting_sell(quantity=1_000_000):
    book = OrderBookCython()
    book.insert_order({
        "order_id": 0, "side": "S", "price": 100.0,
        "quantity": quantity, "timestamp": time.perf_counter_ns(),
    })
    return book


def produce_trade(book, order_id):
    return book.match_order({
        "order_id": order_id, "side": "B", "price": 100.0,
        "quantity": 1, "timestamp": time.perf_counter_ns(),
    })


@pytest.mark.asyncio
async def test_flush_now_persists_pending_trades_immediately():
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=10)  # long interval;
                                                                     # flush_now should
                                                                     # not need to wait for it

    produce_trade(book, 1)
    produce_trade(book, 2)

    inserted = await flusher.flush_now()

    assert inserted == 2
    assert ledger.get_statistics(conn)["total_trades"] == 2
    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_background_loop_flushes_new_trades_automatically():
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=0.02)

    flusher.start()
    for i in range(1, 11):
        produce_trade(book, i)
        await asyncio.sleep(0.005)

    await asyncio.sleep(0.1)  # let the flusher catch up
    await flusher.stop()

    assert ledger.get_statistics(conn)["total_trades"] == 10
    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_flusher_only_sends_new_trades_each_cycle():
    """The core efficiency claim: a flush cycle with no new trades
    since the last one should do no database work (0 inserted), not
    re-send everything again."""
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=10)

    produce_trade(book, 1)
    first_flush_count = await flusher.flush_now()
    second_flush_count = await flusher.flush_now()  # nothing new happened in between

    assert first_flush_count == 1
    assert second_flush_count == 0
    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_pause_stops_flushing_without_stopping_the_task():
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=0.02)

    flusher.start()
    produce_trade(book, 1)
    await asyncio.sleep(0.1)
    count_before_pause = flusher.total_flushed

    flusher.pause()
    produce_trade(book, 2)
    await asyncio.sleep(0.1)
    count_during_pause = flusher.total_flushed

    await flusher.stop()

    assert count_before_pause == 1
    assert count_during_pause == count_before_pause  # nothing new flushed while paused
    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_resume_continues_flushing():
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=0.02)

    flusher.start()
    produce_trade(book, 1)
    await asyncio.sleep(0.1)
    flusher.pause()
    produce_trade(book, 2)
    await asyncio.sleep(0.05)

    flusher.resume()
    await asyncio.sleep(0.1)
    await flusher.stop()

    assert ledger.get_statistics(conn)["total_trades"] == 2
    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_flushed_trade_data_matches_engine_trade_exactly():
    """Every field the engine computed (including Day 12's latency
    instrumentation) should survive the round trip into SQLite
    unchanged."""
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=10)

    result = produce_trade(book, 1)
    engine_trade = result["trades"][0]

    await flusher.flush_now()

    ledger_trades = ledger.get_recent_trades(conn, limit=1)
    ledger_trade = ledger_trades[0]

    assert ledger_trade["trade_id"] == engine_trade["trade_id"]
    assert ledger_trade["buy_order_id"] == engine_trade["buy_order_id"]
    assert ledger_trade["sell_order_id"] == engine_trade["sell_order_id"]
    assert ledger_trade["price"] == engine_trade["price"]
    assert ledger_trade["quantity"] == engine_trade["quantity"]
    assert ledger_trade["entry_timestamp"] == engine_trade["entry_timestamp"]
    assert ledger_trade["exit_timestamp"] == engine_trade["exit_timestamp"]
    assert ledger_trade["latency_ns"] == engine_trade["latency_ns"]

    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_get_stats_shape():
    book = make_book_with_resting_sell()
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=10)

    produce_trade(book, 1)
    await flusher.flush_now()

    stats = flusher.get_stats()
    assert set(stats.keys()) == {
        "total_flushed", "flush_cycles", "last_flushed_index", "last_flush_error"
    }
    assert stats["total_flushed"] == 1
    assert stats["last_flushed_index"] == 1
    assert stats["last_flush_error"] is None

    conn.close()
    os.remove(TEST_DB_PATH)


@pytest.mark.asyncio
async def test_no_trades_no_op_flush():
    """Flushing when nothing has happened yet should be a clean no-op,
    not an error."""
    book = OrderBookCython()  # empty book, no trades possible yet
    conn = fresh_db()
    flusher = TradeFlusher(book, conn, flush_interval_seconds=10)

    inserted = await flusher.flush_now()

    assert inserted == 0
    assert ledger.get_statistics(conn)["total_trades"] == 0
    conn.close()
    os.remove(TEST_DB_PATH)
