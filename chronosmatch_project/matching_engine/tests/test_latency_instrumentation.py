"""
matching_engine/tests/test_latency_instrumentation.py
----------------------------------------------------------
Day 12: tests for the entry/exit timestamp + latency fields added to
every trade. Per spec: "Embed time.perf_counter_ns() timestamps to
measure the exact nanosecond a trade enters and exits the engine."
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


def make_order(order_id, side, price, quantity, timestamp=None):
    return {
        "order_id": order_id, "side": side, "price": price,
        "quantity": quantity,
        "timestamp": timestamp if timestamp is not None else time.perf_counter_ns(),
    }


def test_trade_includes_timestamp_fields():
    """Every trade dict returned by match_order() must carry the three
    new fields, alongside the existing ones from Day 5."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))

    result = book.match_order(make_order(2, "B", 100.0, 10))
    trade = result["trades"][0]

    assert set(trade.keys()) == {
        "trade_id", "buy_order_id", "sell_order_id", "price", "quantity",
        "entry_timestamp", "exit_timestamp", "latency_ns",
    }


def test_entry_timestamp_matches_incoming_orders_own_timestamp():
    """entry_timestamp must reflect the INCOMING (triggering) order's
    own timestamp, not the resting order's --- the resting order may
    have been sitting on the book for an arbitrary, unrelated amount
    of time before this match happened."""
    book = OrderBookCython()
    resting_ts = 1_000_000_000  # deliberately far in the "past"
    book.insert_order(make_order(1, "S", 100.0, 10, timestamp=resting_ts))

    incoming_ts = 5_000_000_000  # a very different value
    result = book.match_order(make_order(2, "B", 100.0, 10, timestamp=incoming_ts))

    assert result["trades"][0]["entry_timestamp"] == incoming_ts
    assert result["trades"][0]["entry_timestamp"] != resting_ts


def test_exit_timestamp_is_after_entry_timestamp():
    """exit_timestamp is measured at match time, strictly after the
    order's own entry_timestamp was set by the caller (some real time
    must always have passed, however small)."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))

    entry_ts = time.perf_counter_ns()
    result = book.match_order(make_order(2, "B", 100.0, 10, timestamp=entry_ts))

    trade = result["trades"][0]
    assert trade["exit_timestamp"] > trade["entry_timestamp"]


def test_latency_ns_equals_exit_minus_entry():
    """latency_ns must be exactly exit_timestamp - entry_timestamp ---
    precomputed inside the engine, verified here rather than assumed."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))

    result = book.match_order(make_order(2, "B", 100.0, 10))
    trade = result["trades"][0]

    assert trade["latency_ns"] == trade["exit_timestamp"] - trade["entry_timestamp"]


def test_latency_is_positive_and_reasonably_small():
    """Sanity bound, not a precise benchmark (see
    audits/engine_verification.py for the full percentile report):
    latency for a single in-process match should be positive and
    well under 1 millisecond on any reasonable machine --- generous
    enough to avoid CI flakiness."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))

    result = book.match_order(make_order(2, "B", 100.0, 10))
    latency_ns = result["trades"][0]["latency_ns"]

    assert 0 < latency_ns < 1_000_000  # under 1ms


def test_multiple_trades_in_one_match_each_get_their_own_timestamps():
    """A single incoming order that walks multiple price levels
    produces multiple trades --- each should carry its own
    exit_timestamp (captured at the moment THAT specific trade was
    recorded, not all sharing one timestamp from before the loop
    started), and all should share the SAME entry_timestamp (all
    triggered by the same incoming order)."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))
    book.insert_order(make_order(3, "S", 102.0, 5))

    incoming_ts = time.perf_counter_ns()
    result = book.match_order(make_order(4, "B", 102.0, 15, timestamp=incoming_ts))

    assert len(result["trades"]) == 3
    for trade in result["trades"]:
        assert trade["entry_timestamp"] == incoming_ts

    # exit timestamps should be non-decreasing across the sequence of
    # trades produced within the same match_order() call (each is
    # captured slightly later than the previous, since they happen in
    # a real sequential loop)
    exit_times = [t["exit_timestamp"] for t in result["trades"]]
    assert exit_times == sorted(exit_times)


def test_c_only_path_also_records_timestamps():
    """The pure-C entry point (run_c_only_matching_cycle, used by the
    GC-safety tests) must also produce properly timestamped trades ---
    confirms the instrumentation lives in the actual hot path
    (_record_trade_c), not bolted on only at the Python-facing edge."""
    book = OrderBookCython()
    book.run_c_only_matching_cycle(1, ord("S"), 100.0, 10, 12345)
    book.run_c_only_matching_cycle(2, ord("B"), 100.0, 10, 99999)

    last_trade = book.get_last_trade()
    assert last_trade["entry_timestamp"] == 99999
    assert last_trade["exit_timestamp"] > 0
    assert last_trade["latency_ns"] == last_trade["exit_timestamp"] - 99999


def test_trades_property_includes_timestamps():
    """The trades property (full trade history view) must also carry
    the new fields, not just the single-trade get_last_trade()."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))
    book.match_order(make_order(2, "B", 100.0, 10))

    all_trades = book.trades
    assert len(all_trades) == 1
    assert "latency_ns" in all_trades[0]
    assert "entry_timestamp" in all_trades[0]
    assert "exit_timestamp" in all_trades[0]
