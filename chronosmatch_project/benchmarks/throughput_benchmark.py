"""
benchmarks/throughput_benchmark.py
-------------------------------------
Day 4: measures actual achievable order throughput, layer by layer,
to find out where the real bottleneck is before claiming any number
against the spec's 100,000 orders/sec target.

Layers measured separately:
1. generate_order() alone — pure order generation, no IPC
2. RingBuffer.write_order() alone — pure IPC write, pre-built orders
3. generate_order() + write_order() together, synchronously, no asyncio
4. MarketFirehose end-to-end (asyncio, with the configured interval)

Why measure layers separately: if the firehose as a whole is slow,
this tells us WHERE the time is going, instead of guessing. A single
end-to-end number alone wouldn't be enough to know what to optimize.

IMPORTANT — environment honesty:
This benchmark reports whatever this specific machine achieves. It is
NOT a substitute for real hardware benchmarking. Single-core cloud
sandboxes, dev laptops, and dedicated trading servers will all produce
very different numbers. Treat the numbers below as "proof the pipeline
works and roughly where the ceiling is on this machine today," not as
a production SLA claim.
"""

import asyncio
import os
import sys
import time

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "matching_engine"))

from shared.ring_buffer import RingBuffer
from simulator.order_generator import generate_order
from simulator.market_firehose import MarketFirehose


def benchmark_generate_order_only(n=50_000):
    start = time.perf_counter()
    for _ in range(n):
        generate_order()
    elapsed = time.perf_counter() - start
    return n / elapsed, elapsed


def benchmark_write_order_only(n=50_000):
    # `with` so the mapping and lock handle are released before the
    # next benchmark re-creates the region at a different capacity.
    with RingBuffer(capacity=1024, create=True) as rb:
        return _timed_write_only(rb, n)


def _timed_write_only(rb, n):
    orders = [generate_order() for _ in range(n)]

    start = time.perf_counter()
    written = 0
    for order in orders:
        if rb.is_full():
            rb.read_order()  # drain one to keep writing, isolate write cost only
        if rb.write_order(order):
            written += 1
    elapsed = time.perf_counter() - start
    return written / elapsed, elapsed


def benchmark_generate_and_write_sync(n=50_000):
    with RingBuffer(capacity=1024, create=True) as rb:
        return _timed_generate_and_write(rb, n)


def _timed_generate_and_write(rb, n):
    start = time.perf_counter()
    written = 0
    for _ in range(n):
        order = generate_order()
        if rb.is_full():
            rb.read_order()
        if rb.write_order(order):
            written += 1
    elapsed = time.perf_counter() - start
    return written / elapsed, elapsed


async def benchmark_firehose_uncapped(duration_seconds=2):
    """Run MarketFirehose with NO artificial interval — i.e. request
    a target rate far above what's achievable, so the real ceiling
    shows up rather than the configured throttle."""
    with RingBuffer(capacity=4096, create=True) as rb:
        return await _run_uncapped(rb, duration_seconds)


async def _run_uncapped(rb, duration_seconds):
    # Ask for an unrealistically high target so the loop never sleeps
    # waiting for its next scheduled tick --- this reveals the actual
    # ceiling instead of the throttle.
    firehose = MarketFirehose(rb, orders_per_second=10_000_000)

    # Drain concurrently so the buffer doesn't fill and mask the
    # generation+write rate behind read-then-retry backoff.
    async def drainer():
        while True:
            if rb.read_order() is None:
                await asyncio.sleep(0)

    firehose.start()
    drain_task = asyncio.ensure_future(drainer())

    await asyncio.sleep(duration_seconds)

    await firehose.stop()
    drain_task.cancel()

    stats = firehose.get_stats()
    return stats["actual_orders_per_second"], stats


def main():
    print("=" * 70)
    print("ChronosMatch — Throughput Benchmark (Day 4)")
    print(f"Machine: {os.cpu_count()} CPU(s) visible to this process")
    print("=" * 70)

    print("\n[1/4] generate_order() alone (pure Python, no IPC)...")
    rate, elapsed = benchmark_generate_order_only()
    print(f"      {rate:,.0f} orders/sec  ({elapsed:.3f}s for 50,000 calls)")

    print("\n[2/4] RingBuffer.write_order() alone (pre-built orders)...")
    rate, elapsed = benchmark_write_order_only()
    print(f"      {rate:,.0f} orders/sec  ({elapsed:.3f}s for 50,000 writes)")

    print("\n[3/4] generate_order() + write_order(), synchronous...")
    rate, elapsed = benchmark_generate_and_write_sync()
    print(f"      {rate:,.0f} orders/sec  ({elapsed:.3f}s for 50,000 orders)")

    print("\n[4/4] MarketFirehose end-to-end, asyncio, uncapped target rate...")
    rate, stats = asyncio.run(benchmark_firehose_uncapped())
    print(f"      {rate:,.0f} orders/sec actually achieved")
    print(f"      full stats: {stats}")

    print("\n" + "=" * 70)
    print("Stages [2], [3] and [4] are all SINGLE-PROCESS measurements:")
    print("in [4] the producer and the drainer share one event loop on one")
    print("thread, so they contend with each other rather than running in")
    print("parallel. Expect [4] to land BELOW the two-process figure, not")
    print("above it -- that is the harness, not the design.")
    print("For the real end-to-end number across two OS processes, run")
    print("audits/ipc_audit.py (1,000,000 orders, verified exactly-once).")
    print()
    print("Spec target: 100,000 orders/sec")
    print("See CHANGELOG.md / TASKS.md Day 4 entry for interpretation")
    print("of these numbers and what they mean for the spec target.")
    print("=" * 70)


if __name__ == "__main__":
    main()
