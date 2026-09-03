"""
engine/benchmarks/engine_benchmark.py
----------------------------------------
Produces the required benchmark report:

    Orders processed : 1,000,000
    p50               : X us
    p95               : X us
    p99               : X us
    p999              : X us
    Max latency       : X us
    Throughput        : X orders/sec

Two latency numbers are reported, for honesty about what each measures:

  EXTERNAL latency: wall-clock time around each individual match_order()
  Python call (time.perf_counter_ns() before/after) -- what a caller
  actually experiences, including dict conversion at the Cython boundary
  and Python call overhead. This is the number the required report format
  above is built from.

  INTERNAL (engine-only) latency: the engine's OWN nanosecond
  entry/exit timestamps on every trade (captured inside the nogil
  matching loop itself, via get_latency_stats()) -- excludes Python
  call/dict overhead entirely. Reported alongside for comparison; it is
  necessarily lower than the external number, and shows how much of the
  external latency is Cython-boundary overhead vs. actual matching cost.

Order flow: prices drawn from a bounded band around a mid-price (so the
book has realistic depth and a meaningful fraction of orders actually
cross), sides random, quantities random -- not an all-match or all-rest
degenerate case.

Run:
    cd engine
    python setup.py build_ext --inplace   (one-time, if not already built)
    python benchmarks/engine_benchmark.py [N]
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from matching_engine import MatchingEngine
except ImportError:
    print("Cython extension not built. Run: cd engine && python setup.py build_ext --inplace")
    sys.exit(1)


DEFAULT_N = 1_000_000
MID_PRICE = 100.0
PRICE_BAND = 2.00      # orders priced within +/- this of the mid, in 0.01 ticks
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


def percentile(sorted_values, pct):
    if not sorted_values:
        return 0.0
    idx = min(int(len(sorted_values) * pct), len(sorted_values) - 1)
    return sorted_values[idx]


def run_benchmark(n: int):
    book = MatchingEngine()
    orders = generate_orders(n)

    external_latencies_ns = [0] * n
    trades_produced = 0
    orders_resting = 0

    t_start = time.perf_counter_ns()
    for i, (order_id, side, price, qty) in enumerate(orders):
        order = {
            "order_id": order_id, "side": side, "price": price,
            "quantity": qty, "timestamp": time.perf_counter_ns(),
        }
        t0 = time.perf_counter_ns()
        result = book.match_order(order)
        t1 = time.perf_counter_ns()

        external_latencies_ns[i] = t1 - t0
        trades_produced += len(result["trades"])
        if result["resting"]:
            orders_resting += 1
    t_end = time.perf_counter_ns()

    total_elapsed_s = (t_end - t_start) / 1e9
    throughput = n / total_elapsed_s

    external_latencies_ns.sort()

    engine_internal_stats = book.get_latency_stats()

    return {
        "n": n,
        "elapsed_s": total_elapsed_s,
        "throughput": throughput,
        "trades_produced": trades_produced,
        "orders_resting": orders_resting,
        "external_sorted_ns": external_latencies_ns,
        "internal_stats": engine_internal_stats,
    }


def print_report(stats):
    ext = stats["external_sorted_ns"]
    n = len(ext)

    def us(ns):
        return ns / 1000.0

    print("=" * 70)
    print("ChronosMatch Matching Engine -- Benchmark")
    print("=" * 70)
    print(f"Orders processed  : {stats['n']:,}")
    print(f"Trades produced   : {stats['trades_produced']:,}")
    print(f"Orders resting    : {stats['orders_resting']:,}")
    print(f"Wall time         : {stats['elapsed_s']:.3f} s")
    print()
    print("External latency (wall-clock around each match_order() call,")
    print("includes dict conversion + Python call overhead):")
    print(f"  p50               : {us(percentile(ext, 0.50)):.2f} us")
    print(f"  p95               : {us(percentile(ext, 0.95)):.2f} us")
    print(f"  p99               : {us(percentile(ext, 0.99)):.2f} us")
    print(f"  p999              : {us(percentile(ext, 0.999)):.2f} us")
    print(f"  Max latency       : {us(ext[-1]):.2f} us")
    print(f"  Throughput        : {stats['throughput']:,.0f} orders/sec")
    print()
    ins = stats["internal_stats"]
    print("Internal (engine-only) latency, measured inside the nogil")
    print("matching loop via perf_counter_ns() -- excludes Python/dict")
    print(f"overhead (n={ins['count']:,} trades):")
    print(f"  p50               : {us(ins['p50_ns']):.2f} us")
    print(f"  p95               : {us(ins['p95_ns']):.2f} us")
    print(f"  p99               : {us(ins['p99_ns']):.2f} us")
    print(f"  p999              : {us(ins['p999_ns']):.2f} us")
    print(f"  Max (lifetime)    : {us(ins['max_ns']):.2f} us")
    print("=" * 70)


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N
    stats = run_benchmark(n)
    print_report(stats)


if __name__ == "__main__":
    main()
