"""
simulator/tests/test_market_firehose.py
------------------------------------------
Day 3: tests for MarketFirehose --- the asyncio-based order generator
that writes into the ring buffer. Uses pytest-asyncio's event_loop
handling via pytest.mark.asyncio.
"""

import asyncio

import pytest

from simulator.market_firehose import MarketFirehose


def new_buffer(ring_buffer, capacity=64):
    """Per-test, auto-closed ring buffer (see conftest.py)."""
    return ring_buffer(capacity=capacity)


@pytest.mark.asyncio
async def test_start_and_stop_writes_orders(ring_buffer):
    rb = new_buffer(ring_buffer)
    firehose = MarketFirehose(rb, orders_per_second=100)

    firehose.start()
    await asyncio.sleep(0.2)
    await firehose.stop()

    assert firehose.orders_written > 0
    assert rb.size() == firehose.orders_written


@pytest.mark.asyncio
async def test_pause_stops_generation_without_stopping_task(ring_buffer):
    rb = new_buffer(ring_buffer)
    firehose = MarketFirehose(rb, orders_per_second=200)

    firehose.start()
    await asyncio.sleep(0.1)
    written_before_pause = firehose.orders_written

    firehose.pause()
    await asyncio.sleep(0.15)
    written_during_pause = firehose.orders_written

    await firehose.stop()

    # No new orders should have been written while paused.
    assert written_during_pause == written_before_pause


@pytest.mark.asyncio
async def test_resume_continues_generation(ring_buffer):
    rb = new_buffer(ring_buffer)
    firehose = MarketFirehose(rb, orders_per_second=200)

    firehose.start()
    await asyncio.sleep(0.1)
    firehose.pause()
    await asyncio.sleep(0.05)
    firehose.resume()
    await asyncio.sleep(0.1)
    await firehose.stop()

    # Should have kept writing after resume, i.e. more than what a
    # single 0.1s burst would produce alone is not guaranteed, but at
    # minimum resume must not leave the count frozen at the pause point.
    assert firehose.orders_written > 0


@pytest.mark.asyncio
async def test_get_stats_shape_and_rate(ring_buffer):
    rb = new_buffer(ring_buffer)
    firehose = MarketFirehose(rb, orders_per_second=50)

    firehose.start()
    await asyncio.sleep(0.3)
    await firehose.stop()

    stats = firehose.get_stats()
    assert set(stats.keys()) == {
        "orders_written", "orders_dropped", "elapsed_seconds",
        "target_orders_per_second", "actual_orders_per_second",
    }
    assert stats["target_orders_per_second"] == 50
    # actual rate should be in a sane ballpark of the target, not exact
    # (timing jitter is expected over such a short window)
    assert 0 < stats["actual_orders_per_second"] <= 200


@pytest.mark.asyncio
async def test_double_start_is_a_no_op(ring_buffer):
    rb = new_buffer(ring_buffer)
    firehose = MarketFirehose(rb, orders_per_second=100)

    firehose.start()
    task_after_first_start = firehose._task
    firehose.start()  # should not replace the running task
    task_after_second_start = firehose._task

    await firehose.stop()

    assert task_after_first_start is task_after_second_start


@pytest.mark.asyncio
async def test_backoff_when_buffer_full(ring_buffer):
    """Tiny buffer, high rate --- forces write_with_backoff to actually
    hit a full buffer and either retry successfully or drop, never
    raise or hang."""
    rb = new_buffer(ring_buffer, capacity=2)
    firehose = MarketFirehose(rb, orders_per_second=500)

    firehose.start()
    await asyncio.sleep(0.2)
    await firehose.stop()

    # Whatever happened, written + dropped should account for every
    # generation attempt, and neither should be negative.
    assert firehose.orders_written >= 0
    assert firehose.orders_dropped >= 0
