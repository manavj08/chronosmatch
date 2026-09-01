"""
simulator/market_simulator.py
--------------------------------
Asyncio market data firehose: generates realistic Buy/Sell tick data and
writes it into the zero-copy IPC ring buffer (ipc.RingBuffer), the way a
websocket client consuming a real Nasdaq/NYSE feed would hand ticks off
to a downstream consumer -- a single async event loop, non-blocking,
many "ticks" conceptually in flight rather than one blocking loop.

Honest framing: this does not connect to a real market data feed --
there is no live exchange connection in scope here. What "asyncio
firehose" means is architectural: built the way a real websocket-
consuming client would be, even though the ticks themselves are
generated locally. If a real feed is ever wired in, only "where ticks
come from" changes -- the asyncio plumbing around it does not.

Realistic order generation:
    - Buy/Sell: configurable probability split (default 50/50).
    - Prices: drawn from a bounded set of discrete price LEVELS around a
      mid-price (a fixed tick size), not a continuous uniform range --
      this is what "different price levels" means for an order book:
      many orders should land on the SAME price so the book actually
      has depth at each level, the way a real market does, rather than
      every order being at its own unique price.
    - Quantities: random within a configurable range.
    - Order IDs: monotonically increasing, unique per generated order.
    - Bursts: periodically (configurable probability per tick), the
      generator temporarily multiplies its effective rate for a short
      window -- simulating a real burst of activity (e.g. a wave of
      orders immediately following an earnings report), not just a
      constant steady-state rate.

Throughput technique (why asyncio.sleep() is not called once per
order): a naive "generate one order, sleep, repeat" loop is capped by
how fast asyncio's own timer scheduling can fire wakeups, not by how
fast order generation + the IPC write actually are -- measured
elsewhere in this project at roughly 55,000 sleep-wakeups/sec on a
single-core sandbox, regardless of how fast the actual work is. Fixed
by picking a tick length (default 10ms) and, each tick, writing as many
orders as the target rate implies for that slice of time, then sleeping
once for whatever's left of the tick -- trading a small amount of
burstiness (orders arrive in small batches every 10ms rather than
perfectly evenly spaced) for throughput that scales with the target
rate instead of being capped by timer-wakeup frequency.
"""

import asyncio
import os
import random
import sys
import time

if __name__ == "__main__":
    # Allow running this file directly (python simulator/market_simulator.py)
    # in addition to `python -m simulator.market_simulator` / normal package
    # import -- both need the project root (parent of ipc/ and simulator/)
    # on sys.path.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipc.ring_buffer import RingBuffer

# ----------------------------------------------------------------------
# Configuration (kept as module-level constants, overridable via
# MarketSimulator's constructor args, rather than hardcoded inline --
# same reasoning as the rest of this project's config modules: these
# values get tuned/read from more than one place).
# ----------------------------------------------------------------------
ORDERS_PER_SECOND = 1000

MID_PRICE = 100.00
PRICE_TICK = 0.01          # smallest price increment -- real exchanges
                             # trade in fixed ticks, not continuous reals
PRICE_LEVELS_EACH_SIDE = 50  # distinct price levels above/below mid;
                               # e.g. 50 levels * 0.01 tick = a $0.50 band

MIN_QUANTITY = 1
MAX_QUANTITY = 500
BUY_PROBABILITY = 0.5

BURST_PROBABILITY_PER_TICK = 0.01  # chance, each 10ms tick, that a
                                     # burst window starts
BURST_MULTIPLIER = 8                # effective rate during a burst
BURST_DURATION_SECONDS = 0.5

TICK_SECONDS = 0.01


class OrderIdGenerator:
    """Monotonically increasing, unique order ids. A plain instance
    attribute (not a module global) so multiple independent simulators
    in the same process don't share a counter unless explicitly told
    to."""

    def __init__(self, start: int = 1):
        self._next_id = start

    def next(self) -> int:
        order_id = self._next_id
        self._next_id += 1
        return order_id


def generate_order(order_id_gen: OrderIdGenerator,
                    mid_price: float = MID_PRICE,
                    price_tick: float = PRICE_TICK,
                    price_levels_each_side: int = PRICE_LEVELS_EACH_SIDE,
                    min_quantity: int = MIN_QUANTITY,
                    max_quantity: int = MAX_QUANTITY,
                    buy_probability: float = BUY_PROBABILITY) -> dict:
    """Build one random, realistic order.

    Price is snapped to one of a bounded set of discrete levels around
    `mid_price` (a real tick size, `price_tick` apart) rather than a
    continuous uniform draw, so repeated calls naturally cluster many
    orders onto the SAME price -- real order-book depth, not every
    order landing at its own unique price.
    """
    side = "B" if random.random() < buy_probability else "S"
    level_offset = random.randint(-price_levels_each_side, price_levels_each_side)
    price = round(mid_price + level_offset * price_tick, 2)
    quantity = random.randint(min_quantity, max_quantity)

    return {
        "order_id": order_id_gen.next(),
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


class MarketSimulator:
    """
    Async order generator + ring-buffer writer.

    start()/stop()/pause()/resume() -- start_simulation/stop_simulation/
    pause_simulation/resume_simulation, named to fit asyncio conventions
    here since this class IS the simulator's async entry point.
    """

    def __init__(self, ring_buffer: RingBuffer, orders_per_second: int = None,
                 mid_price: float = MID_PRICE, price_tick: float = PRICE_TICK,
                 price_levels_each_side: int = PRICE_LEVELS_EACH_SIDE,
                 min_quantity: int = MIN_QUANTITY, max_quantity: int = MAX_QUANTITY,
                 buy_probability: float = BUY_PROBABILITY,
                 burst_probability_per_tick: float = BURST_PROBABILITY_PER_TICK,
                 burst_multiplier: float = BURST_MULTIPLIER,
                 burst_duration_seconds: float = BURST_DURATION_SECONDS,
                 enable_bursts: bool = True):
        self.ring_buffer = ring_buffer
        self.orders_per_second = orders_per_second or ORDERS_PER_SECOND
        self.mid_price = mid_price
        self.price_tick = price_tick
        self.price_levels_each_side = price_levels_each_side
        self.min_quantity = min_quantity
        self.max_quantity = max_quantity
        self.buy_probability = buy_probability

        self.enable_bursts = enable_bursts
        self.burst_probability_per_tick = burst_probability_per_tick
        self.burst_multiplier = burst_multiplier
        self.burst_duration_seconds = burst_duration_seconds
        self._burst_until = 0.0  # perf_counter() timestamp; "in a burst" while now < this

        self._order_id_gen = OrderIdGenerator()
        self._running = False
        self._paused = False
        self._task: asyncio.Task | None = None

        self.orders_written = 0
        self.orders_dropped = 0  # buffer stayed full past the retry budget
        self.burst_ticks = 0     # how many ticks fired while a burst was active
        self._start_time: float | None = None

    def _current_orders_per_tick(self, tick_seconds: float) -> int:
        """Effective orders-per-tick, accounting for an active burst
        window. Bursts are decided once per tick (probabilistically) and
        then held active for burst_duration_seconds, rather than being
        an instant single-tick spike, so a burst looks like a real
        sustained wave of volume rather than a single anomalous batch."""
        now = time.perf_counter()
        if self.enable_bursts and now >= self._burst_until:
            if random.random() < self.burst_probability_per_tick:
                self._burst_until = now + self.burst_duration_seconds

        in_burst = now < self._burst_until
        if in_burst:
            self.burst_ticks += 1
            rate = self.orders_per_second * self.burst_multiplier
        else:
            rate = self.orders_per_second

        return max(1, round(rate * tick_seconds))

    async def _run(self):
        tick_seconds = TICK_SECONDS
        self._start_time = time.perf_counter()

        while self._running:
            if self._paused:
                await asyncio.sleep(0.05)
                continue

            tick_start = time.perf_counter()
            orders_this_tick = self._current_orders_per_tick(tick_seconds)

            for _ in range(orders_this_tick):
                if not self._running:
                    break
                order = generate_order(
                    self._order_id_gen, self.mid_price, self.price_tick,
                    self.price_levels_each_side, self.min_quantity,
                    self.max_quantity, self.buy_probability,
                )
                written = await self._write_with_backoff(order)
                if written:
                    self.orders_written += 1
                else:
                    self.orders_dropped += 1

            # Sleep only for whatever time is LEFT in the tick, not the
            # full tick length regardless of how long the batch took --
            # otherwise, at high target rates, the batch work eats into
            # the tick and the loop undershoots the target rate.
            batch_elapsed = time.perf_counter() - tick_start
            remaining = tick_seconds - batch_elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)

    async def _write_with_backoff(self, order: dict, max_retries: int = 5) -> bool:
        """Try to write; if the buffer is full, yield control briefly
        and retry a bounded number of times rather than blocking forever
        or busy-looping."""
        for attempt in range(max_retries):
            if self.ring_buffer.write_order(order):
                return True
            await asyncio.sleep(0.001 * (attempt + 1))
        return False

    def start(self):
        """start_simulation() equivalent. Must be called from within a
        running asyncio event loop."""
        if self._running:
            return
        self._running = True
        self._paused = False
        self.orders_written = 0
        self.orders_dropped = 0
        self.burst_ticks = 0
        self._task = asyncio.ensure_future(self._run())

    async def stop(self):
        """stop_simulation() equivalent. Awaits the internal task so the
        caller knows generation has actually ceased."""
        self._running = False
        if self._task is not None:
            await self._task
            self._task = None

    def pause(self):
        """pause_simulation() equivalent. Loop keeps running but stops
        generating/writing until resume()."""
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
            "burst_ticks": self.burst_ticks,
        }


async def _demo():
    """Manual smoke test: run the simulator for a few seconds at a
    small rate and print stats + a sample of the buffer's contents."""
    rb = RingBuffer(capacity=256, create=True, backing_file="/tmp/market_simulator_demo.mem")
    sim = MarketSimulator(rb, orders_per_second=200)

    sim.start()
    await asyncio.sleep(3)
    await sim.stop()

    print("simulator stats:", sim.get_stats())
    print("buffer stats:", rb.get_stats())

    print("\nsample of orders still resting in the buffer:")
    for _ in range(5):
        order = rb.read_order()
        if order is None:
            break
        print(" ", order)


if __name__ == "__main__":
    asyncio.run(_demo())
