"""
engine/benchmarks/benchmark_vs_python.py
--------------------------------------------
Benchmarks the optimized Cython engine (matching_engine.pyx --
price-level-bucketed, C structs, nogil hot path) against the "earlier
implementation" (python_baseline_engine.py -- plain Python lists, linear
scan/insert, real matching logic but no optimization at all).

Both engines run the EXACT SAME generated order sequence, so the
comparison isolates implementation cost, not workload differences.

Run:
    cd engine
    python setup.py build_ext --inplace   (one-time, if not already built)
    python benchmarks/benchmark_vs_python.py [N]
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from matching_engine import MatchingEngine
except ImportError:
    print("Cython extension not built. Run: cd engine && python setup.py build_ext --inplace")
    sys.exit(1)

from python_baseline_engine import PythonBaselineOrderBook


DEFAULT_N = 50_000   # smaller than the 1M-order Cython-only benchmark --
                       # the pure-Python O(n) baseline is slow enough that
                       # 1M orders would take a very long time to finish.
MID_PRICE = 100.0
PRICE_BAND = 2.00
PRICE_TICK = 0.01
MIN_QTY = 1
MAX_QTY = 50
SEED = 42


def generate_orders(n: int):
    rng = random.Random(SEED)
    n_ticks = int(PRICE_BAND / PRICE_TICK)
    orders = []
    for i in range(n):
        side = "B" if rng.random() < 0.5 else "S"
        offset_ticks = rng.randint(-n_ticks, n_ticks)
        price = round(MID_PRICE + offset_ticks * PRICE_TICK, 2)
        qty = rng.randint(MIN_QTY, MAX_QTY)
        orders.append((i + 1, side, price, qty))
    return orders


def run_cython(orders):
    book = MatchingEngine()
    t0 = time.perf_counter_ns()
    trades = 0
    for order_id, side, price, qty in orders:
        result = book.match_order({
            "order_id": order_id, "side": side, "price": price,
            "quantity": qty, "timestamp": time.perf_counter_ns(),
        })
        trades += len(result["trades"])
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1e9, trades


def run_python_baseline(orders):
    book = PythonBaselineOrderBook()
    t0 = time.perf_counter_ns()
    trades = 0
    for order_id, side, price, qty in orders:
        result = book.match_order({
            "order_id": order_id, "side": side, "price": price,
            "quantity": qty, "timestamp": time.perf_counter_ns(),
        })
        trades += len(result["trades"])
    t1 = time.perf_counter_ns()
    return (t1 - t0) / 1e9, trades


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
    orders = generate_orders(n)

    print("=" * 70)
    print("Cython (optimized) vs. pure-Python (earlier/unoptimized) engine")
    print("=" * 70)
    print(f"Order sequence: {n:,} orders (identical input to both engines)")
    print()

    py_elapsed, py_trades = run_python_baseline(orders)
    py_throughput = n / py_elapsed
    print("Pure-Python baseline (plain lists, O(n) linear insert/scan):")
    print(f"  Elapsed      : {py_elapsed:.3f} s")
    print(f"  Trades       : {py_trades:,}")
    print(f"  Throughput   : {py_throughput:,.0f} orders/sec")
    print()

    cy_elapsed, cy_trades = run_cython(orders)
    cy_throughput = n / cy_elapsed
    print("Cython engine (price-level bucketing, C structs, nogil hot path):")
    print(f"  Elapsed      : {cy_elapsed:.3f} s")
    print(f"  Trades       : {cy_trades:,}")
    print(f"  Throughput   : {cy_throughput:,.0f} orders/sec")
    print()

    assert py_trades == cy_trades, (
        f"Trade count mismatch ({py_trades} vs {cy_trades}) -- the two "
        f"engines disagree on matching outcomes for the same input; "
        f"the speed comparison is only meaningful if they agree."
    )

    speedup = cy_throughput / py_throughput
    print("=" * 70)
    print(f"Both engines produced the same {cy_trades:,} trades from the "
          f"same input (correctness cross-check passed).")
    print(f"Cython engine is {speedup:.1f}x faster than the pure-Python "
          f"baseline on this run.")
    print("=" * 70)


if __name__ == "__main__":
    main()
