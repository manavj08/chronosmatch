"""
matching_engine/tests/test_trade_history_slicing.py
--------------------------------------------------------
Day 14: tests for get_trades_since() and trade_count --- the engine
surface added to support database/trade_flusher.py's incremental
flushing (pull only new trades since the last flush, not the whole
history every cycle).
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from order_book import OrderBookCython
except ImportError:
    pytest.skip(
        "Cython extension not built. Run: python setup_demo.py",
        allow_module_level=True,
    )


def book_with_n_trades(n):
    book = OrderBookCython()
    book.insert_order({"order_id": 0, "side": "S", "price": 100.0,
                        "quantity": 1_000_000, "timestamp": time.perf_counter_ns()})
    for i in range(n):
        book.match_order({"order_id": i + 1, "side": "B", "price": 100.0,
                           "quantity": 1, "timestamp": time.perf_counter_ns()})
    return book


def test_trade_count_matches_actual_trades_produced():
    book = book_with_n_trades(15)
    assert book.trade_count == 15
    assert len(book.trades) == 15


def test_get_trades_since_zero_returns_everything():
    book = book_with_n_trades(10)
    trades = book.get_trades_since(0)
    assert len(trades) == 10
    assert trades[0]["trade_id"] == 1
    assert trades[-1]["trade_id"] == 10


def test_get_trades_since_middle_returns_only_newer_trades():
    book = book_with_n_trades(10)
    trades = book.get_trades_since(5)
    assert len(trades) == 5
    assert [t["trade_id"] for t in trades] == [6, 7, 8, 9, 10]


def test_get_trades_since_current_count_returns_empty():
    book = book_with_n_trades(10)
    trades = book.get_trades_since(book.trade_count)
    assert trades == []


def test_get_trades_since_beyond_count_returns_empty_not_error():
    book = book_with_n_trades(10)
    trades = book.get_trades_since(1000)
    assert trades == []


def test_get_trades_since_negative_index_treated_as_zero():
    book = book_with_n_trades(5)
    trades = book.get_trades_since(-10)
    assert len(trades) == 5


def test_incremental_pulls_cover_full_history_with_no_gaps_or_overlap():
    """Simulates exactly what trade_flusher.py does: repeatedly call
    get_trades_since(last_seen), advancing last_seen by how many were
    returned each time --- the union of all pulls must equal the full
    trade history with no trade missing and none duplicated."""
    book = book_with_n_trades(1)  # start book, then interleave pulls with new trades
    all_pulled_ids = []
    last_seen = 0

    for batch in range(5):
        for i in range(3):
            book.match_order({
                "order_id": 1000 + batch * 3 + i, "side": "B", "price": 100.0,
                "quantity": 1, "timestamp": time.perf_counter_ns(),
            })
        new_trades = book.get_trades_since(last_seen)
        all_pulled_ids.extend(t["trade_id"] for t in new_trades)
        last_seen = book.trade_count

    expected_ids = list(range(1, book.trade_count + 1))
    assert all_pulled_ids == expected_ids


def test_get_trades_since_on_empty_book():
    book = OrderBookCython()
    assert book.trade_count == 0
    assert book.get_trades_since(0) == []
