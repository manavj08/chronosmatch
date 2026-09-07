"""
simulator/load_test.py
-------------------------
Graduated load test: runs MarketFirehose against increasing target
rates (10k, 50k, 100k, 150k, ... orders/sec) and measures the ACTUAL
achieved throughput at each one, to find where the pipeline's
throughput starts falling behind the requested target -- i.e. where it
"breaks down" -- rather than only reporting a single uncapped ceiling
(that's what benchmarks/throughput_benchmark.py already measures; this
script answers a different question: not "what's the max", but "at
what target rate does reality start missing the target").

Each target rate runs for a fixed duration with a concurrent drainer
consuming from the ring buffer, so the firehose never waits on a
buffer that's genuinely full because nothing is reading it -- this
isolates the firehose + IPC pipeline's own throughput, not the
reader's.

Run:
    python simulator/load_test.py                  # default rate sweep
    python simulator/load_test.py 10000 50000 200000 500000   # custom targets

Honesty note (same as the rest of this project's benchmarks): these are
real numbers for whatever machine this runs on, not a production
hardware claim.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from shared.ring_buffer import RingBuffer
from shared.shared_memory import reset_shared_region
from simulator.market_firehose import MarketFirehose

DEFAULT_TARGETS = [10_000, 50_000, 100_000, 150_000, 200_000, 300_000, 500_000]
RUN_DURATION_SECONDS = 2.0
BREAKDOWN_THRESHOLD = 0.70  # "broken down" = achieved < 70% of target


async def run_one_rate(target_rate: int, duration: float = RUN_DURATION_SECONDS) -> dict:
    """Run the firehose at `target_rate` for `duration` seconds with a
    concurrent drainer, and report the actual achieved throughput."""
    # Each call starts from a clean region. reset_shared_region() also
    # clears the .lock file and releases the creating handle --- doing
    # this by hand used to leave the previous run's mapping open, so on
    # Windows the next iteration could not delete the file it had just
    # been told to replace.
    reset_shared_region(8192)

    rb = RingBuffer(capacity=8192, create=False)
    firehose = MarketFirehose(rb, orders_per_second=target_rate)

    drained = 0

    async def drainer():
        nonlocal drained
        while True:
            if rb.read_order() is not None:
                drained += 1
            else:
                await asyncio.sleep(0)

    firehose.start()
    drain_task = asyncio.ensure_future(drainer())

    await asyncio.sleep(duration)

    await firehose.stop()
    drain_task.cancel()
    try:
        await drain_task
    except asyncio.CancelledError:
        pass

    stats = firehose.get_stats()
    rb.close()  # release the mapping so the next rate can reset the region
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
    print("Spec target: 100,000 orders/sec -- see the table above for where")
    print("this specific machine sits relative to it.")
    print()
    print("IMPORTANT -- what this sweep does and does not measure.")
    print("Producer and consumer here are two asyncio tasks sharing ONE")
    print("event loop in ONE process. They take turns on a single thread,")
    print("so this measures how the design behaves under self-contention,")
    print("not its capacity. It is a deliberately pessimistic figure and a")
    print("good regression signal, but it is NOT the number to quote")
    print("against the spec target.")
    print()
    print("The architecture the spec describes -- and the one the project")
    print("actually ships -- is a producer PROCESS and a consumer PROCESS")
    print("on separate cores. For that, run:")
    print()
    print("    python audits/ipc_audit.py")
    print()
    print("which sends 1,000,000 orders between two real OS processes and")
    print("verifies every one arrives exactly once, in order. That is the")
    print("authoritative end-to-end throughput measurement.")
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
