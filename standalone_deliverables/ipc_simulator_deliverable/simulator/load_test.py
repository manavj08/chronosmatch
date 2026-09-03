"""
simulator/load_test.py
-------------------------
Graduated load test: runs the market simulator against increasing
target rates (10k, 50k, 100k, 150k, ... orders/sec) and measures the
ACTUAL achieved throughput at each one, to find where the pipeline's
throughput starts falling behind the requested target -- i.e. where it
"breaks down" -- rather than just reporting a single uncapped number.

Each target rate runs for a fixed duration with a concurrent drainer
consuming from the ring buffer (so the producer never has to wait on a
buffer that's genuinely full because nothing is reading it -- this
isolates the SIMULATOR + IPC pipeline's throughput, not the reader's).

Run:
    python simulator/load_test.py                  # default rate sweep
    python simulator/load_test.py 10000 50000 200000 500000   # custom targets

Honesty note (same as the rest of this project's benchmarks): these are
real numbers for whatever machine this runs on, not a production
hardware claim. Single-core sandboxes, laptops, and dedicated trading
servers will all report different breakdown points.
"""

import asyncio
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipc.ring_buffer import RingBuffer
from simulator.market_simulator import MarketSimulator

DEFAULT_TARGETS = [10_000, 50_000, 100_000, 150_000, 200_000, 300_000, 500_000]
RUN_DURATION_SECONDS = 2.0
BREAKDOWN_THRESHOLD = 0.70  # "broken down" = achieved < 70% of target


async def run_one_rate(target_rate: int, duration: float = RUN_DURATION_SECONDS) -> dict:
    """Run the simulator at `target_rate` for `duration` seconds with a
    concurrent drainer, and report the actual achieved throughput."""
    backing_file = f"/tmp/load_test_{target_rate}.mem"
    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)

    rb = RingBuffer(capacity=8192, create=True, backing_file=backing_file)
    sim = MarketSimulator(rb, orders_per_second=target_rate, enable_bursts=False)

    drained = 0

    async def drainer():
        nonlocal drained
        while True:
            if rb.read_order() is not None:
                drained += 1
            else:
                await asyncio.sleep(0)

    sim.start()
    drain_task = asyncio.ensure_future(drainer())

    await asyncio.sleep(duration)

    await sim.stop()
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass

    stats = sim.get_stats()

    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)

    return {
        "target": target_rate,
        "achieved": stats["actual_orders_per_second"],
        "written": stats["orders_written"],
        "dropped": stats["orders_dropped"],
        "drained": drained,
        "pct_of_target": (stats["actual_orders_per_second"] / target_rate * 100) if target_rate else 0,
    }


async def run_sweep(targets: list) -> list:
    results = []
    for target in targets:
        result = await run_one_rate(target)
        results.append(result)
    return results


def find_breakdown_point(results: list):
    """First target rate where achieved throughput fell below
    BREAKDOWN_THRESHOLD of what was requested, or None if the whole
    sweep stayed healthy."""
    for r in results:
        if r["achieved"] < r["target"] * BREAKDOWN_THRESHOLD:
            return r
    return None


def print_report(results: list):
    print("=" * 78)
    print("ChronosMatch -- Graduated Load Test")
    print("=" * 78)
    print(f"{'Target/sec':>12}  {'Achieved/sec':>13}  {'% of target':>11}  "
          f"{'Written':>10}  {'Dropped':>9}")
    print("-" * 78)
    for r in results:
        print(f"{r['target']:>12,}  {r['achieved']:>13,.0f}  {r['pct_of_target']:>10.1f}%  "
              f"{r['written']:>10,}  {r['dropped']:>9,}")
    print("=" * 78)

    breakdown = find_breakdown_point(results)
    if breakdown:
        print(f"Throughput breaks down at target={breakdown['target']:,}/sec: "
              f"achieved only {breakdown['achieved']:,.0f}/sec "
              f"({breakdown['pct_of_target']:.1f}% of target, below the "
              f"{BREAKDOWN_THRESHOLD*100:.0f}% threshold).")
        healthy = [r for r in results if r["target"] < breakdown["target"]]
        if healthy:
            print(f"Highest target rate still sustained above threshold: "
                  f"{healthy[-1]['target']:,}/sec "
                  f"({healthy[-1]['achieved']:,.0f}/sec achieved, "
                  f"{healthy[-1]['pct_of_target']:.1f}% of target).")
    else:
        print(f"No breakdown found within the tested range -- every target "
              f"rate up to {results[-1]['target']:,}/sec was sustained above "
              f"{BREAKDOWN_THRESHOLD*100:.0f}% of its target.")
    print("=" * 78)


def main():
    if len(sys.argv) > 1:
        targets = [int(a) for a in sys.argv[1:]]
    else:
        targets = DEFAULT_TARGETS

    print(f"Sweeping {len(targets)} target rates, {RUN_DURATION_SECONDS}s each: "
          f"{', '.join(f'{t:,}' for t in targets)}\n")

    results = asyncio.run(run_sweep(targets))
    print_report(results)


if __name__ == "__main__":
    main()
