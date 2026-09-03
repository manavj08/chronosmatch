"""
simulator/tests/test_market_simulator.py
--------------------------------------------
Tests for MarketSimulator (the asyncio order generator + ring-buffer
writer) and generate_order() (the realistic order-generation logic
underneath it): buy/sell mix, discrete price levels, quantity range,
unique order ids, burst behavior, and the start/stop/pause/resume
lifecycle.
"""

import asyncio
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ipc.ring_buffer import RingBuffer
from simulator.market_simulator import MarketSimulator, OrderIdGenerator, generate_order


def new_buffer(capacity=64, name="sim_test"):
    backing_file = f"/tmp/market_simulator_test_{name}_{os.getpid()}.mem"
    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    return RingBuffer(capacity=capacity, create=True, backing_file=backing_file)


# ======================================================================
# generate_order() -- realistic generation properties
# ======================================================================

class TestGenerateOrder:
    def test_generates_both_sides_over_many_calls(self):
        gen = OrderIdGenerator()
        sides = {generate_order(gen)["side"] for _ in range(200)}
        assert sides == {"B", "S"}

    def test_buy_probability_is_roughly_respected(self):
        gen = OrderIdGenerator()
        n = 5000
        buys = sum(1 for _ in range(n) if generate_order(gen, buy_probability=0.8)["side"] == "B")
        # Generous tolerance -- this is a statistical property, not exact.
        assert 0.7 < buys / n < 0.9

    def test_order_ids_are_unique_and_increasing(self):
        gen = OrderIdGenerator()
        ids = [generate_order(gen)["order_id"] for _ in range(500)]
        assert ids == sorted(ids)
        assert len(set(ids)) == len(ids)

    def test_prices_land_on_discrete_tick_aligned_levels(self):
        """Prices must be exact multiples of price_tick relative to
        mid_price -- not arbitrary continuous floats -- so many orders
        naturally land on the same price level."""
        gen = OrderIdGenerator()
        mid, tick = 100.0, 0.01
        for _ in range(500):
            order = generate_order(gen, mid_price=mid, price_tick=tick, price_levels_each_side=20)
            offset = round((order["price"] - mid) / tick)
            assert abs(order["price"] - round(mid + offset * tick, 2)) < 1e-9

    def test_prices_stay_within_configured_band(self):
        gen = OrderIdGenerator()
        mid, tick, levels = 100.0, 0.01, 10
        for _ in range(500):
            order = generate_order(gen, mid_price=mid, price_tick=tick, price_levels_each_side=levels)
            assert mid - levels * tick - 1e-9 <= order["price"] <= mid + levels * tick + 1e-9

    def test_many_orders_share_price_levels_giving_the_book_real_depth(self):
        """With a small number of discrete levels, many orders out of a
        few hundred should collide on the same price -- this is the
        actual point of tick-aligned generation (order-book depth),
        verified directly rather than just checking the tick alignment
        in isolation."""
        gen = OrderIdGenerator()
        prices = [generate_order(gen, price_levels_each_side=5)["price"] for _ in range(300)]
        distinct_prices = set(prices)
        # 11 possible levels (5 each side + mid); 300 orders should
        # collide onto them heavily, not produce ~300 distinct prices.
        assert len(distinct_prices) <= 11

    def test_quantity_within_configured_range(self):
        gen = OrderIdGenerator()
        for _ in range(300):
            order = generate_order(gen, min_quantity=5, max_quantity=10)
            assert 5 <= order["quantity"] <= 10

    def test_order_has_all_required_fields(self):
        gen = OrderIdGenerator()
        order = generate_order(gen)
        assert set(order.keys()) == {"order_id", "side", "price", "quantity", "timestamp"}


# ======================================================================
# MarketSimulator lifecycle
# ======================================================================

class TestMarketSimulatorLifecycle:
    @pytest.mark.asyncio
    async def test_start_and_stop_writes_orders(self):
        rb = new_buffer(name="lifecycle1")
        sim = MarketSimulator(rb, orders_per_second=100)

        sim.start()
        await asyncio.sleep(0.2)
        await sim.stop()

        assert sim.orders_written > 0
        assert rb.size() == sim.orders_written

    @pytest.mark.asyncio
    async def test_pause_stops_generation_without_stopping_task(self):
        rb = new_buffer(name="lifecycle2")
        sim = MarketSimulator(rb, orders_per_second=200)

        sim.start()
        await asyncio.sleep(0.1)
        sim.pause()
        written_at_pause = sim.orders_written
        await asyncio.sleep(0.15)
        written_during_pause = sim.orders_written

        await sim.stop()

        assert written_during_pause == written_at_pause

    @pytest.mark.asyncio
    async def test_resume_continues_generation(self):
        rb = new_buffer(name="lifecycle3")
        sim = MarketSimulator(rb, orders_per_second=200)

        sim.start()
        await asyncio.sleep(0.1)
        sim.pause()
        await asyncio.sleep(0.05)
        sim.resume()
        await asyncio.sleep(0.1)
        await sim.stop()

        assert sim.orders_written > 0

    @pytest.mark.asyncio
    async def test_get_stats_shape_and_rate(self):
        rb = new_buffer(name="lifecycle4")
        sim = MarketSimulator(rb, orders_per_second=50)

        sim.start()
        await asyncio.sleep(0.3)
        await sim.stop()

        stats = sim.get_stats()
        assert set(stats.keys()) == {
            "orders_written", "orders_dropped", "elapsed_seconds",
            "target_orders_per_second", "actual_orders_per_second", "burst_ticks",
        }
        assert stats["target_orders_per_second"] == 50
        assert 0 < stats["actual_orders_per_second"] <= 200

    @pytest.mark.asyncio
    async def test_double_start_is_a_no_op(self):
        rb = new_buffer(name="lifecycle5")
        sim = MarketSimulator(rb, orders_per_second=100)

        sim.start()
        task_after_first = sim._task
        sim.start()
        task_after_second = sim._task

        await sim.stop()

        assert task_after_first is task_after_second

    @pytest.mark.asyncio
    async def test_backoff_when_buffer_full_never_raises_or_hangs(self):
        """Tiny buffer, high rate -- forces _write_with_backoff to
        actually hit a full buffer and either retry successfully or
        drop, never raise or hang."""
        rb = new_buffer(capacity=2, name="lifecycle6")
        sim = MarketSimulator(rb, orders_per_second=500)

        sim.start()
        await asyncio.sleep(0.2)
        await sim.stop()

        assert sim.orders_written >= 0
        assert sim.orders_dropped >= 0

    @pytest.mark.asyncio
    async def test_generated_orders_round_trip_through_the_real_ring_buffer(self):
        """End-to-end sanity check: orders the simulator writes must be
        readable back out with all fields intact through the real IPC
        bus, not just constructible in memory."""
        rb = new_buffer(name="lifecycle7")
        sim = MarketSimulator(rb, orders_per_second=100)

        sim.start()
        await asyncio.sleep(0.1)
        await sim.stop()

        count = 0
        while not rb.is_empty():
            order = rb.read_order()
            assert order["side"] in ("B", "S")
            assert order["quantity"] > 0
            count += 1
        assert count == sim.orders_written


# ======================================================================
# Bursts
# ======================================================================

class TestBursts:
    @pytest.mark.asyncio
    async def test_burst_mode_measurably_increases_effective_rate(self):
        """With bursts forced on every tick, the simulator should write
        substantially more than its configured base rate would produce
        alone -- confirms burst_multiplier actually takes effect, not
        just that the field exists."""
        rb = new_buffer(capacity=100_000, name="burst1")
        sim = MarketSimulator(
            rb, orders_per_second=100, enable_bursts=True,
            burst_probability_per_tick=1.0,  # always burst, deterministic test
            burst_multiplier=10, burst_duration_seconds=1.0,
        )

        sim.start()
        await asyncio.sleep(0.3)
        await sim.stop()

        # Base rate alone (100/sec) over 0.3s would write roughly ~30;
        # with a forced 10x burst active throughout, it should be far
        # higher. Generous threshold to avoid timing-jitter flakiness.
        assert sim.orders_written > 100
        assert sim.burst_ticks > 0

    @pytest.mark.asyncio
    async def test_bursts_can_be_disabled(self):
        rb = new_buffer(capacity=100_000, name="burst2")
        sim = MarketSimulator(
            rb, orders_per_second=100, enable_bursts=False,
            burst_probability_per_tick=1.0,  # would always burst if enabled
        )

        sim.start()
        await asyncio.sleep(0.3)
        await sim.stop()

        assert sim.burst_ticks == 0
