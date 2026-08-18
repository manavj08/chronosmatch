"""
simulator/tests/test_firehose_throughput.py
----------------------------------------------
Day 4: automated regression test for throughput, not just the manual
benchmarks/throughput_benchmark.py script. This guards against a
future change silently reintroducing the Day 4 bottleneck (calling
asyncio.sleep() once per single order instead of batching per tick).

Deliberately NOT asserting the full 100,000/sec spec target here ---
CI/test machines are often slower and noisier than a dev machine or
target deployment hardware, and a flaky throughput test that fails on
an unrelated slow CI runner is worse than no test. Instead this
asserts a much lower floor that would only fail if the batching
optimization regressed back to the old per-order-sleep design.
"""

import asyncio

import pytest

from shared.ring_buffer import RingBuffer
from simulator.market_firehose import MarketFirehose


@pytest.mark.asyncio
async def test_firehose_sustains_high_throughput_not_just_low():
    """Regression guard: with a high target rate and a fast drainer,
    achieved throughput should be well above what the OLD (pre-Day-4)
    per-order-sleep design could sustain (~55k/sec was the measured
    ceiling on the benchmark machine before batching). This threshold
    is set conservatively below that regression point, not at the
    100k/sec target itself, to avoid CI flakiness."""
    rb = RingBuffer(capacity=2048, create=True)
    firehose = MarketFirehose(rb, orders_per_second=1_000_000)

    async def drainer():
        while True:
            if rb.read_order() is None:
                await asyncio.sleep(0)

    firehose.start()
    drain_task = asyncio.ensure_future(drainer())

    await asyncio.sleep(1.0)

    await firehose.stop()
    drain_task.cancel()

    stats = firehose.get_stats()
    # Old per-order-sleep design measured ~55k/sec ceiling; this floor
    # is set well below the ~100-200k/sec the batched design achieves,
    # to tolerate slower/noisier CI machines while still catching a
    # real regression back to the old per-order-sleep pattern.
    assert stats["actual_orders_per_second"] > 60_000, (
        f"Throughput regressed: {stats['actual_orders_per_second']} "
        f"orders/sec — expected the Day 4 batching fix to sustain "
        f"well above the old ~55k/sec per-order-sleep ceiling"
    )


@pytest.mark.asyncio
async def test_firehose_approaches_configured_target_rate():
    """At a moderate, achievable target rate, actual throughput should
    land reasonably close to what was requested — not wildly under,
    which was the Day 4 bug (100k/sec target only achieving ~75k/sec
    before the tick-timing fix)."""
    rb = RingBuffer(capacity=2048, create=True)
    target = 20_000
    firehose = MarketFirehose(rb, orders_per_second=target)

    async def drainer():
        while True:
            if rb.read_order() is None:
                await asyncio.sleep(0)

    firehose.start()
    drain_task = asyncio.ensure_future(drainer())

    await asyncio.sleep(1.0)

    await firehose.stop()
    drain_task.cancel()

    stats = firehose.get_stats()
    # Allow generous tolerance for slower test machines: at least 50%
    # of target. The point is catching a gross undershoot bug, not
    # pinning an exact number.
    assert stats["actual_orders_per_second"] > target * 0.5
