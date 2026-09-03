"""
audits/engine_verification.py
--------------------------------
Day 9: MID-PROJECT REVIEW (second half) --- "Prove the Order Book
correctly matches a Buy order with a corresponding Sell order
instantly."

Day 5's matching_engine/tests/test_matching.py already proves
CORRECTNESS thoroughly (12 unit tests: full match, partial match,
multi-level walking, price limits, time priority, trade bookkeeping)
--- calling match_order() directly against an in-memory OrderBookCython.
That's necessary but not sufficient for this specific spec line: it
doesn't touch the word "instantly," and it doesn't exercise the real
end-to-end path (ring buffer -> engine) the way production order flow
actually would.

This script covers what Day 5's unit tests don't:

1. CORRECTNESS THROUGH THE REAL PIPELINE: orders enter via
   shared.ring_buffer.RingBuffer.write_order() (the same entry point
   real order flow uses, e.g. simulator/market_firehose.py), get read
   back with read_order(), and THEN matched --- not constructed as a
   dict and handed directly to match_order() in memory, which is what
   every Day 5 test does.

2. "INSTANTLY", MEASURED, NOT ASSERTED: wall-clock time from the
   moment an order is written into the ring buffer to the moment its
   resulting trade is recorded, using time.perf_counter_ns() (matches
   the spec's stated instrumentation tool, ahead of the full latency
   pipeline scheduled for Day 12). Reports actual microsecond
   numbers rather than just asserting "it works."

Honesty notes:
- This is single-process (writer and matcher in the same process,
  sequential) specifically to isolate match latency itself from IPC
  scheduling/OS context-switch noise between two separate processes
  (that's what Day 8's audit already measures, at throughput scale,
  not per-order latency). A future day could add a two-process
  latency variant if that distinction matters for the final report.
- These are real measurements, but on a single-core sandbox machine
  (see benchmarks/throughput_benchmark.py's honesty note) --- not a
  production hardware latency guarantee.
- "Instantly" has no universal formal definition here; this script
  reports the actual measured numbers and a rough categorization
  (microseconds vs. milliseconds), and leaves the "is that fast
  enough" judgment to the reader rather than asserting a specific
  arbitrary threshold as pass/fail. What's verified as pass/fail is
  CORRECTNESS (does it match the way it should); latency numbers are
  reported alongside as evidence, not as a hard-coded threshold gate.

Run:
    python setup_demo.py         (one-time, if not already built)
    python audits/engine_verification.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "matching_engine"))

from shared.ring_buffer import RingBuffer

SAMPLE_SIZE = 10_000  # number of buy/sell pairs to measure for the latency distribution


def verify_single_match_correctness():
    """The literal spec claim, minimal form: one Buy order matches one
    corresponding Sell order, through the real ring buffer pipeline,
    not an in-memory dict handed directly to match_order()."""
    from order_book import OrderBookCython

    backing_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ring_buffer.mem")
    lock_file = backing_file + ".lock"
    for path in (backing_file, lock_file):
        if os.path.exists(path):
            os.remove(path)

    rb = RingBuffer(capacity=16, create=True)
    book = OrderBookCython()

    sell_order = {"order_id": 1, "side": "S", "price": 100.0,
                  "quantity": 10, "timestamp": time.perf_counter_ns()}
    buy_order = {"order_id": 2, "side": "B", "price": 100.0,
                 "quantity": 10, "timestamp": time.perf_counter_ns()}

    # Real pipeline: write into shared memory, read back, THEN match ---
    # not match_order(sell_order) called directly on a dict literal.
    rb.write_order(sell_order)
    received_sell = rb.read_order()
    book.match_order(received_sell)  # rests on the book, nothing to match yet

    rb.write_order(buy_order)
    received_buy = rb.read_order()
    result = book.match_order(received_buy)

    correct = (
        len(result["trades"]) == 1
        and result["trades"][0]["buy_order_id"] == 2
        and result["trades"][0]["sell_order_id"] == 1
        and result["trades"][0]["quantity"] == 10
        and result["resting"] is False
    )
    return correct, result


def measure_match_latency():
    """Measures wall-clock time from write_order() (order enters the
    real shared-memory pipeline) to the matching trade being recorded,
    across SAMPLE_SIZE buy/sell pairs. Each pair: a resting sell is
    seeded once; the timed portion covers only the incoming buy's
    journey through the pipeline to producing a trade."""
    from order_book import OrderBookCython

    rb = RingBuffer(capacity=64, create=True)
    book = OrderBookCython()

    latencies_ns = []

    for i in range(SAMPLE_SIZE):
        sell_id = i * 2 + 1
        buy_id = i * 2 + 2

        sell_order = {"order_id": sell_id, "side": "S", "price": 100.0,
                      "quantity": 1, "timestamp": time.perf_counter_ns()}
        rb.write_order(sell_order)
        book.match_order(rb.read_order())  # rests, sets up the match target

        buy_order = {"order_id": buy_id, "side": "B", "price": 100.0,
                     "quantity": 1, "timestamp": 0}

        t_start = time.perf_counter_ns()
        rb.write_order(buy_order)
        received = rb.read_order()
        result = book.match_order(received)
        t_end = time.perf_counter_ns()

        assert len(result["trades"]) == 1, f"expected a match at iteration {i}, got {result}"
        latencies_ns.append(t_end - t_start)

    return latencies_ns


def summarize(latencies_ns: list) -> dict:
    sorted_ns = sorted(latencies_ns)
    n = len(sorted_ns)
    return {
        "count": n,
        "min_us": sorted_ns[0] / 1000,
        "p50_us": sorted_ns[n // 2] / 1000,
        "p99_us": sorted_ns[int(n * 0.99)] / 1000,
        "max_us": sorted_ns[-1] / 1000,
        "mean_us": sum(sorted_ns) / n / 1000,
    }


def main():
    print("=" * 70)
    print("ChronosMatch — Mid-Project Review: Engine Verification (Day 9)")
    print("=" * 70)

    print("\n[1/2] Correctness: does a Buy instantly match a corresponding Sell,")
    print("      through the real ring-buffer pipeline (not a direct in-memory call)?")
    correct, result = verify_single_match_correctness()
    print(f"      Result: {result}")
    print(f"      {'PASS' if correct else 'FAIL'}: Buy correctly matched the resting Sell.")

    if not correct:
        print("\nVERIFICATION FAILED — see result above.")
        sys.exit(1)

    print(f"\n[2/2] Latency: measuring write_order() -> trade-recorded time")
    print(f"      across {SAMPLE_SIZE:,} buy/sell pairs...")
    latencies_ns = measure_match_latency()
    stats = summarize(latencies_ns)

    print(f"\n      Samples:  {stats['count']:,}")
    print(f"      Min:      {stats['min_us']:.2f} µs")
    print(f"      Mean:     {stats['mean_us']:.2f} µs")
    print(f"      p50:      {stats['p50_us']:.2f} µs")
    print(f"      p99:      {stats['p99_us']:.2f} µs")
    print(f"      Max:      {stats['max_us']:.2f} µs")

    print("\n" + "=" * 70)
    print("VERIFICATION PASSED: a Buy order correctly and repeatably matches")
    print("a corresponding Sell order through the real pipeline.")
    print(f"Typical (p50) latency on this machine: {stats['p50_us']:.2f} microseconds.")
    print("(Single-core sandbox measurement — see this script's module")
    print(" docstring for what that does and doesn't prove about production")
    print(" hardware. Day 12 added the engine's own internal nanosecond")
    print(" entry/exit instrumentation on every trade -- see")
    print(" matching_engine/tests/test_latency_instrumentation.py.)")
    print("=" * 70)


if __name__ == "__main__":
    main()
