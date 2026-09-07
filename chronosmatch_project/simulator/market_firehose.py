"""
simulator/market_firehose.py
-------------------------------
MEMBER B'S MARKET FIREHOSE (Day 3).

Per spec: "Build the asyncio script that blasts mock trade orders
into the IPC bus... simulating a firehose of Nasdaq/NYSE financial
tick data" via a websocket-style client.

Honest framing: this does NOT connect to a real Nasdaq/NYSE feed ---
there's no live market data source in scope for this project. What
"websocket client" means here is architectural: the firehose is built
the way a real websocket-consuming client would be (a single async
event loop, non-blocking, many concurrent "ticks" in flight rather
than one blocking loop) even though the orders themselves are
randomly generated locally, same as order_generator.py did
synchronously in Day 2. If a real market data feed is ever wired in
later, only the "where ticks come from" half of this file changes ---
the asyncio plumbing around it does not.

Why asyncio helps here even with a local generator: write_order() is
fast but not instant (it takes a lock), and under a full buffer it
needs to retry. asyncio lets many "virtual" order-generation tasks
be in flight and yield cleanly while waiting, instead of one thread
doing everything in lockstep --- this is what actually lets the rate
scale toward the spec's 100,000 orders/sec target (Day 4).

Replaces: the synchronous generate_order() loop that
order_generator.py exposed on its own in Day 2.  order_generator.py
itself is UNCHANGED --- generate_order() is still the function that
builds one random order; this file is what drives it at scale,
asynchronously, and writes the result into the ring buffer.
"""

import asyncio
import time

from shared.ring_buffer import RingBuffer
from simulator import config
from simulator.order_generator import generate_order


class MarketFirehose:
    """
    Async order generator + ring-buffer writer.

    start()/stop()/pause()/resume() match the shape the spec asks for
    (start_simulation/stop_simulation/pause_simulation/resume_simulation),
    named to fit asyncio conventions here since this class IS the
    simulator's async entry point.
    """

    def __init__(self, ring_buffer: RingBuffer, orders_per_second: int = None):
        self.ring_buffer = ring_buffer
        self.orders_per_second = orders_per_second or config.ORDERS_PER_SECOND

        self._running = False
        self._paused = False
        self._task: asyncio.Task | None = None

        # Stats, useful for Day 4's throughput measurement and for the
        # eventual dashboard.
        self.orders_written = 0
        self.orders_dropped = 0  # buffer was full and stayed full past retry budget
        self._start_time: float | None = None

    async def _run(self):
        """
        Day 4 change: batches orders per event-loop tick instead of
        calling asyncio.sleep() once per single order.

        Why: the Day 3 benchmark (see benchmarks/throughput_benchmark.py)
        found that asyncio.sleep() with a real (even tiny) delay costs
        far more than the actual order generation + write work — on the
        benchmark machine, roughly 147,000 sleep-calls/sec is the ceiling
        for that pattern alone, regardless of how fast write_order() is.
        Sleeping once per order caps total throughput at whatever rate
        asyncio's timer scheduling can sustain, not at what the IPC pipe
        or the CPU can actually do.

        Fix: pick a tick length (default 10ms) and, each tick, write
        as many orders as the target rate implies for that slice of
        time, then sleep once for the tick. This trades a small amount
        of burstiness (orders arrive in small batches every 10ms
        instead of perfectly evenly spaced) for dramatically higher
        achievable throughput --- and it's a closer match to how a
        real high-rate feed behaves anyway (bursty, not perfectly
        metronomic).
        """
        tick_seconds = 0.01
        orders_per_tick = max(1, round(self.orders_per_second * tick_seconds))
        self._start_time = time.perf_counter()

        while self._running:
            if self._paused:
                await asyncio.sleep(0.05)
                continue

            tick_start = time.perf_counter()

            for _ in range(orders_per_tick):
                if not self._running:
                    break
                order = generate_order()
                written = await self._write_with_backoff(order)
                if written:
                    self.orders_written += 1
                else:
                    self.orders_dropped += 1

            # Day 4 fix: sleep only for whatever time is LEFT in the
            # tick, not the full tick_seconds regardless of how long
            # the batch itself took. Without this, at high target
            # rates the batch work eats into the tick and the loop
            # ends up sleeping too much relative to the target rate,
            # undershooting it (measured: 100k/sec target only
            # achieved ~75k/sec actual before this fix).
            batch_elapsed = time.perf_counter() - tick_start
            remaining = tick_seconds - batch_elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

    # Number of retries that yield to the event loop without arming a
    # real timer. See _write_with_backoff for why this matters.
    _FREE_YIELD_RETRIES = 2

    async def _write_with_backoff(self, order: dict, max_retries: int = 5) -> bool:
        """Try to write; if the buffer is full, yield control briefly
        and retry a bounded number of times rather than blocking
        forever or busy-looping.

        Day 9 fix: the first retries now use `asyncio.sleep(0)` --- a
        pure yield to the event loop --- instead of going straight to
        `asyncio.sleep(0.001)`.

        Why: "buffer is full" almost always means the consumer simply
        has not been scheduled yet. A bare yield hands control to it
        immediately and costs nothing. `asyncio.sleep(0.001)` instead
        arms a real timer, and a 1 ms request is not honoured as 1 ms
        on every platform --- on Windows the event loop's wait
        granularity is the system timer tick (~15.6 ms by default), so
        a "1 ms" backoff can stall the producer for over fifteen
        milliseconds while the consumer drains the buffer in a
        fraction of that and then sits idle. At a high target rate the
        buffer fills on every tick, so that stall was being paid
        continuously and was capping measured throughput at roughly
        55k orders/sec on Windows regardless of how fast the IPC layer
        itself ran. Real timed backoff is still used after a couple of
        yields, for the genuine case where the consumer is actually
        slower than the producer and spinning would waste CPU.
        """
        for attempt in range(max_retries):
            if self.ring_buffer.write_order(order):
                return True
            if attempt < self._FREE_YIELD_RETRIES:
                await asyncio.sleep(0)  # yield, no timer
            else:
                await asyncio.sleep(0.001 * (attempt - self._FREE_YIELD_RETRIES + 1))
        return False

    def start(self):
        """start_simulation() equivalent. Must be called from within
        a running asyncio event loop."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self.orders_written = 0
        self.orders_dropped = 0
        self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        """stop_simulation() equivalent. Awaits the internal task so
        the caller knows generation has actually ceased."""
        self._running = False
        if self._task is not None:
            await self._task
            self._task = None

    def pause(self):
        """pause_simulation() equivalent. Loop keeps running but
        stops generating/writing until resume()."""
        self._paused = True

    def resume(self):
        """resume_simulation() equivalent."""
        self._paused = False

    def get_stats(self) -> dict:
        elapsed = (time.perf_counter() - self._start_time) if self._start_time else 0
        actual_rate = self.orders_written / elapsed if elapsed > 0 else 0
        return {
            "orders_written": self.orders_written,
            "orders_dropped": self.orders_dropped,
            "elapsed_seconds": round(elapsed, 3),
            "target_orders_per_second": self.orders_per_second,
            "actual_orders_per_second": round(actual_rate, 1),
        }


async def _demo():
    """Manual smoke test: run the firehose for 3 seconds at a small
    rate and print stats. Real throughput testing against the spec's
    100,000/sec target happens Day 4."""
    with RingBuffer(capacity=256, create=True) as rb:
        firehose = MarketFirehose(rb, orders_per_second=50)

        firehose.start()
        await asyncio.sleep(3)
        await firehose.stop()

        print("stats:", firehose.get_stats())
        print("buffer stats:", rb.get_stats())


if __name__ == "__main__":
    asyncio.run(_demo())
