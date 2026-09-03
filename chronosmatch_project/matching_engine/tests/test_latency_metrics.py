"""
matching_engine/tests/test_latency_metrics.py
--------------------------------------------------
Day 13: tests for get_latency_stats() --- the live latency metrics
pipeline built on top of Day 12's per-trade entry/exit timestamps.

Covers: empty-state shape, basic percentile ordering (min <= p50 <=
p99 <= p999 <= max), the fixed-size ring buffer's wraparound behavior
(lifetime count stays exact even past LATENCY_RING_SIZE, while
percentiles reflect only the most recent window), and that querying
stats doesn't disturb the matching engine's own state.
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


def seed_and_produce_trades(book, count, base_quantity=1_000_000):
    """Seeds one large resting sell and produces `count` matching buy
    trades against it, one unit each."""
    book.insert_order({"order_id": 0, "side": "S", "price": 100.0,
                        "quantity": base_quantity, "timestamp": 0})
    for i in range(count):
        book.match_order({
            "order_id": i + 1, "side": "B", "price": 100.0,
            "quantity": 1, "timestamp": time.perf_counter_ns(),
        })


def test_empty_book_returns_zeroed_stats_not_an_error():
    book = OrderBookCython()
    stats = book.get_latency_stats()

    assert stats["count"] == 0
    assert stats["min_ns"] == 0
    assert stats["mean_ns"] == 0
    assert stats["max_ns"] == 0
    assert stats["p50_ns"] == 0
    assert stats["p95_ns"] == 0
    assert stats["p99_ns"] == 0
    assert stats["p999_ns"] == 0


def test_stats_shape_has_all_expected_fields():
    book = OrderBookCython()
    seed_and_produce_trades(book, 100)
    stats = book.get_latency_stats()

    assert set(stats.keys()) == {
        "count", "min_ns", "mean_ns", "max_ns",
        "p50_ns", "p95_ns", "p99_ns", "p999_ns",
    }


def test_percentiles_are_correctly_ordered():
    """min <= p50 <= p99 <= p999 <= max must always hold, by
    definition of what a percentile means."""
    book = OrderBookCython()
    seed_and_produce_trades(book, 2000)
    stats = book.get_latency_stats()

    assert stats["min_ns"] <= stats["p50_ns"]
    assert stats["p50_ns"] <= stats["p95_ns"]
    assert stats["p95_ns"] <= stats["p99_ns"]
    assert stats["p99_ns"] <= stats["p999_ns"]
    assert stats["p999_ns"] <= stats["max_ns"]


def test_lifetime_count_exact_even_below_ring_capacity():
    book = OrderBookCython()
    seed_and_produce_trades(book, 500)
    stats = book.get_latency_stats()

    assert stats["count"] == 500


def test_lifetime_count_stays_exact_past_ring_capacity():
    """The circular ring buffer holds at most LATENCY_RING_SIZE
    (10,000) recent samples, but the lifetime `count` field must stay
    exact regardless --- it's tracked separately via an O(1) running
    counter, not derived from the ring's contents."""
    book = OrderBookCython()
    seed_and_produce_trades(book, 12_000)
    stats = book.get_latency_stats()

    assert stats["count"] == 12_000


def test_mean_is_consistent_with_lifetime_sum_and_count():
    """mean_ns is a lifetime average (sum/count), not windowed like
    the percentiles --- verify it's computed correctly by
    cross-checking against the trades property's own latency values
    for a small, exactly-countable batch."""
    book = OrderBookCython()
    seed_and_produce_trades(book, 200)

    all_trades = book.trades
    actual_latencies = [t["latency_ns"] for t in all_trades]
    expected_mean = sum(actual_latencies) // len(actual_latencies)

    stats = book.get_latency_stats()
    assert stats["mean_ns"] == expected_mean


def test_querying_stats_does_not_disturb_book_state():
    """get_latency_stats() sorts a COPY of the ring buffer --- calling
    it repeatedly must not change the book's own matching state or
    corrupt the ring for future trades."""
    book = OrderBookCython()
    seed_and_produce_trades(book, 100)

    stats_first = book.get_latency_stats()
    stats_second = book.get_latency_stats()
    stats_third = book.get_latency_stats()

    assert stats_first == stats_second == stats_third

    # Book should still be fully functional afterward --- more trades
    # should work normally and be reflected in a subsequent query.
    seed_and_produce_trades(book, 50)
    stats_after_more = book.get_latency_stats()
    assert stats_after_more["count"] == 150


def test_single_trade_all_percentiles_equal_that_one_latency():
    book = OrderBookCython()
    seed_and_produce_trades(book, 1)
    stats = book.get_latency_stats()

    assert stats["count"] == 1
    assert (stats["min_ns"] == stats["p50_ns"] == stats["p95_ns"]
            == stats["p99_ns"] == stats["p999_ns"] == stats["max_ns"])
