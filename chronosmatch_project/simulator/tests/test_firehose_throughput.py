"""
simulator/tests/test_firehose_throughput.py
----------------------------------------------
Day 4: automated regression test for throughput, not just the manual
benchmarks/throughput_benchmark.py script. This guards against a
future change silently reintroducing the Day 4 bottleneck (calling
asyncio.sleep() once per single order instead of batching per tick).

Day 9 rewrite --- why the threshold is now relative, not absolute.

The original version asserted a hardcoded floor of 60,000 orders/sec.
That number was calibrated on one developer's machine, and it encoded
two things at once: how fast the async plumbing is, and how fast the
IPC layer underneath it is. The second half does not transfer between
machines or operating systems. Cross-process locking costs a syscall
per acquire and release, and Windows' msvcrt.locking is materially
more expensive than POSIX flock --- so a Windows run measured ~54,700
orders/sec and failed a threshold a Linux run cleared easily, even
though nothing about the batching design had regressed. A test that
fails because of the OS it runs on is not measuring what its name
claims to measure.

So this file now measures the machine's own raw IPC ceiling first ---
plain synchronous write/read pairs, no asyncio anywhere --- and then
asserts the firehose achieves a healthy fraction of it. That makes the
test portable while asserting something stronger than the old absolute
number did: that the async layer is not the bottleneck. If someone
reintroduces a per-order sleep, the firehose rate collapses to a small
fraction of the raw ceiling and this test fails on any machine, which
is exactly the regression it exists to catch.

The full 100,000/sec spec target is still NOT asserted here. Whether a
given machine reaches it depends on that machine's lock throughput;
benchmarks/throughput_benchmark.py remains the place to measure
absolute numbers against the spec.
"""

import asyncio
import time

import pytest

from simulator.market_firehose import MarketFirehose
from simulator.order_generator import generate_order

# The firehose does strictly more work per order than the raw loop (it
# also generates each order and runs an event loop), so it can never
# reach 100% of the raw ceiling. Measured at roughly 76% on the
# reference Linux machine after the Day 9 backoff fix. 40% leaves
# generous headroom for slower and noisier machines while still
# sitting far above where a per-order-sleep regression would land.
MIN_FRACTION_OF_RAW_CEILING = 0.40

# A floor that would only be crossed if something is broken outright
# rather than merely slow. Deliberately low.
ABSOLUTE_SANITY_FLOOR = 5_000

MEASURE_SECONDS = 1.0
RAW_CEILING_SAMPLES = 20_000


def _measure_raw_ipc_ceiling(rb, samples=RAW_CEILING_SAMPLES):
    """Orders/sec for plain synchronous write+read pairs.

    This is the hard ceiling the async layer sits under on this
    particular machine: serialization plus two lock acquire/release
    cycles per order, with no event loop involved at all.
    """
    order = generate_order()
    start = time.perf_counter()
    for _ in range(samples):
        rb.write_order(order)
        rb.read_order()
    elapsed = time.perf_counter() - start
    return samples / elapsed


async def _run_firehose(rb, target_rate, seconds=MEASURE_SECONDS):
    """Run the firehose against a draining consumer and report stats."""
    firehose = MarketFirehose(rb, orders_per_second=target_rate)

    async def drainer():
        while True:
            if rb.read_order() is None:
                await asyncio.sleep(0)

    firehose.start()
    drain_task = asyncio.ensure_future(drainer())
    try:
        await asyncio.sleep(seconds)
        await firehose.stop()
    finally:
        drain_task.cancel()

    return firehose.get_stats()


@pytest.mark.asyncio
async def test_firehose_sustains_high_throughput_not_just_low(ring_buffer):
    """Regression guard: with a high target rate and a fast drainer,
    the firehose should sustain a healthy fraction of what the IPC
    layer alone can do on this machine.

    The old per-order-sleep design could not: it arms one timer per
    order, so throughput is pinned to the event loop's timer rate
    rather than to the IPC layer, landing far below this threshold no
    matter how fast the underlying buffer is.
    """
    rb = ring_buffer(capacity=2048)

    raw_ceiling = _measure_raw_ipc_ceiling(rb)
    assert rb.is_empty(), "measurement loop should leave the buffer drained"

    stats = await _run_firehose(rb, target_rate=1_000_000)
    actual = stats["actual_orders_per_second"]

    assert actual > ABSOLUTE_SANITY_FLOOR, (
        f"Throughput collapsed to {actual:,.0f} orders/sec, far below "
        f"anything this design should produce --- something is broken "
        f"rather than merely slow."
    )

    floor = raw_ceiling * MIN_FRACTION_OF_RAW_CEILING
    assert actual > floor, (
        f"Throughput regressed: {actual:,.0f} orders/sec against a raw "
        f"IPC ceiling of {raw_ceiling:,.0f} orders/sec on this machine "
        f"({actual / raw_ceiling:.0%} of it, expected at least "
        f"{MIN_FRACTION_OF_RAW_CEILING:.0%}). The async layer, not the "
        f"IPC layer, is the bottleneck --- check whether a per-order "
        f"asyncio.sleep() has crept back into the write path."
    )


@pytest.mark.asyncio
async def test_firehose_approaches_configured_target_rate(ring_buffer):
    """At a moderate, achievable target rate, actual throughput should
    land reasonably close to what was requested --- not wildly under,
    which was the Day 4 bug (100k/sec target only achieving ~75k/sec
    before the tick-timing fix)."""
    rb = ring_buffer(capacity=2048)
    target = 20_000

    stats = await _run_firehose(rb, target_rate=target)

    # Generous tolerance for slower test machines: at least 50% of
    # target. The point is catching a gross undershoot bug, not
    # pinning an exact number.
    assert stats["actual_orders_per_second"] > target * 0.5, (
        f"Requested {target:,}/sec but achieved "
        f"{stats['actual_orders_per_second']:,.0f}/sec"
    )


@pytest.mark.asyncio
async def test_full_buffer_backoff_does_not_stall_the_producer(ring_buffer):
    """Day 9 regression guard for the backoff path specifically.

    With a buffer far too small for the target rate, every tick hits
    "buffer full" and goes through _write_with_backoff. Those first
    retries must be bare event-loop yields, not armed timers: a timer
    per full-buffer retry stalls the producer for at least one timer
    tick (~15.6 ms on Windows by default) while the consumer drains in
    a fraction of that and then sits idle. This test fails if the
    backoff goes back to sleeping on every retry.
    """
    rb = ring_buffer(capacity=4)

    stats = await _run_firehose(rb, target_rate=1_000_000, seconds=0.5)

    assert stats["orders_written"] > 1_000, (
        f"Only {stats['orders_written']} orders got through a "
        f"constantly-full buffer in half a second --- the backoff path "
        f"is stalling the producer on a real timer instead of yielding."
    )
