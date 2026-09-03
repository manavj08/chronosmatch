"""
engine/tests/test_order_book.py
--------------------------------
Day 1: confirms OrderBook now reads from the REAL shared-memory
RingBuffer (Member A's shared/ package), not the old fake stub.

Matching logic itself (insert_order / match_order) is still a
placeholder --- see TASKS.md, Day 2-4. These tests only cover the
Day 1 wiring change.
"""

import time

from engine.order_book import OrderBook
from shared.ring_buffer import RingBuffer


def make_order(order_id, side, price, quantity):
    return {
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


def test_order_book_uses_real_ring_buffer():
    rb = RingBuffer(capacity=4, create=True)
    book = OrderBook(ring_buffer=rb)

    rb.write_order(make_order(1, "B", 101.0, 10))
    processed = book.process_next()

    assert processed is not None
    assert processed["order_id"] == 1
    assert len(book.buy_side) == 1


def test_process_next_returns_none_when_buffer_empty():
    rb = RingBuffer(capacity=4, create=True)
    book = OrderBook(ring_buffer=rb)

    assert book.process_next() is None


def test_get_top_levels_shape():
    rb = RingBuffer(capacity=4, create=True)
    book = OrderBook(ring_buffer=rb)

    levels = book.get_top_levels()
    assert "bids" in levels
    assert "asks" in levels


def test_multiple_orders_through_real_buffer():
    rb = RingBuffer(capacity=4, create=True)
    book = OrderBook(ring_buffer=rb)

    rb.write_order(make_order(1, "B", 101.0, 10))
    rb.write_order(make_order(2, "S", 100.5, 5))

    first = book.process_next()
    second = book.process_next()

    assert first["order_id"] == 1
    assert second["order_id"] == 2
    assert book.process_next() is None
    assert len(book.buy_side) == 1
    assert len(book.sell_side) == 1
