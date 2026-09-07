"""
matching_engine/tests/test_engine_verification.py
------------------------------------------------------
Day 9: automated pytest coverage for the Mid-Project Review's
"Engine Verification" requirement, alongside the standalone report
script (audits/engine_verification.py).

Day 5's test_matching.py already proves matching correctness
thoroughly by calling match_order() directly on in-memory dicts. This
file specifically covers what that doesn't: correctness through the
REAL ring-buffer pipeline (write_order -> read_order -> match_order),
and a basic latency sanity check (not a precise benchmark --- see
audits/engine_verification.py for the full latency report with
percentiles; this test just guards against a gross regression, e.g.
someone accidentally reintroducing a sleep() or an O(n) scan into the
hot path).
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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))


@pytest.fixture
def fresh_ring_buffer(ring_buffer):
    """Per-test, auto-closed ring buffer.

    Was a plain helper that deleted the one global backing file and
    built a buffer nobody ever closed. Each RingBuffer holds an fd on
    the lock file, and on Windows an open handle makes that file
    undeletable --- so the next test's cleanup failed with WinError 32.
    The `ring_buffer` fixture in conftest.py gives each test its own
    file and closes everything afterwards.
    """
    def _make(capacity=64):
        return ring_buffer(capacity=capacity)
    return _make


def test_buy_matches_sell_through_real_ring_buffer_pipeline(fresh_ring_buffer):
    """The literal spec claim: a Buy correctly matches a corresponding
    Sell --- through the REAL pipeline (ring buffer write + read),
    not a dict handed directly to match_order()."""
    rb = fresh_ring_buffer()
    book = OrderBookCython()

    sell_order = {"order_id": 1, "side": "S", "price": 100.0,
                  "quantity": 10, "timestamp": time.perf_counter_ns()}
    buy_order = {"order_id": 2, "side": "B", "price": 100.0,
                 "quantity": 10, "timestamp": time.perf_counter_ns()}

    rb.write_order(sell_order)
    book.match_order(rb.read_order())  # rests on the book

    rb.write_order(buy_order)
    result = book.match_order(rb.read_order())

    assert len(result["trades"]) == 1
    assert result["trades"][0]["buy_order_id"] == 2
    assert result["trades"][0]["sell_order_id"] == 1
    assert result["trades"][0]["quantity"] == 10
    assert result["resting"] is False


def test_sell_matches_buy_through_real_ring_buffer_pipeline(fresh_ring_buffer):
    """Same as above, opposite direction --- both sides of "instantly
    matches a corresponding order" per the spec wording."""
    rb = fresh_ring_buffer()
    book = OrderBookCython()

    buy_order = {"order_id": 1, "side": "B", "price": 100.0,
                 "quantity": 5, "timestamp": time.perf_counter_ns()}
    sell_order = {"order_id": 2, "side": "S", "price": 100.0,
                  "quantity": 5, "timestamp": time.perf_counter_ns()}

    rb.write_order(buy_order)
    book.match_order(rb.read_order())

    rb.write_order(sell_order)
    result = book.match_order(rb.read_order())

    assert len(result["trades"]) == 1
    assert result["trades"][0]["buy_order_id"] == 1
    assert result["trades"][0]["sell_order_id"] == 2


def test_repeated_matches_through_pipeline_stay_correct(fresh_ring_buffer):
    """Runs several match cycles through the real pipeline in sequence
    --- guards against state leaking between orders (e.g. a stale
    read/write pointer, or trade_id not advancing correctly) that a
    single-pair test wouldn't catch."""
    rb = fresh_ring_buffer()
    book = OrderBookCython()

    for i in range(20):
        sell_id, buy_id = i * 2 + 1, i * 2 + 2
        rb.write_order({"order_id": sell_id, "side": "S", "price": 100.0,
                         "quantity": 1, "timestamp": i})
        book.match_order(rb.read_order())

        rb.write_order({"order_id": buy_id, "side": "B", "price": 100.0,
                         "quantity": 1, "timestamp": i})
        result = book.match_order(rb.read_order())

        assert len(result["trades"]) == 1
        assert result["trades"][0]["sell_order_id"] == sell_id
        assert result["trades"][0]["buy_order_id"] == buy_id
        assert result["trades"][0]["trade_id"] == i + 1


def test_match_latency_through_pipeline_is_reasonable(fresh_ring_buffer):
    """Regression guard, not a precise benchmark (see
    audits/engine_verification.py for the full percentile report).
    Median latency through the real pipeline should stay comfortably
    under 1 millisecond --- generous enough to avoid CI flakiness on
    a slow/shared machine, but tight enough to catch a gross
    regression like an accidentally introduced sleep() or per-order
    O(n) scan."""
    rb = fresh_ring_buffer(capacity=64)
    book = OrderBookCython()

    latencies_ns = []
    sample_size = 500  # smaller than the full report's 10,000, for test speed

    for i in range(sample_size):
        sell_id, buy_id = i * 2 + 1, i * 2 + 2
        rb.write_order({"order_id": sell_id, "side": "S", "price": 100.0,
                         "quantity": 1, "timestamp": 0})
        book.match_order(rb.read_order())

        t_start = time.perf_counter_ns()
        rb.write_order({"order_id": buy_id, "side": "B", "price": 100.0,
                         "quantity": 1, "timestamp": 0})
        result = book.match_order(rb.read_order())
        t_end = time.perf_counter_ns()

        assert len(result["trades"]) == 1
        latencies_ns.append(t_end - t_start)

    latencies_ns.sort()
    median_us = latencies_ns[len(latencies_ns) // 2] / 1000

    assert median_us < 1000, (
        f"Median match latency through the real pipeline was "
        f"{median_us:.2f} microseconds --- expected well under 1000µs "
        f"(1ms). This is a regression guard threshold, not the spec's "
        f"actual <50µs target (see audits/engine_verification.py for "
        f"the full percentile report against that target)."
    )
