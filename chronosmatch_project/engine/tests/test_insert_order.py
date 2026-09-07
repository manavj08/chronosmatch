"""
engine/tests/test_insert_order.py
-----------------------------------
Day 2: confirms insert_order() keeps each side sorted by price
(best price first) instead of the old plain-append placeholder.

match_order() itself is still a placeholder --- these tests call
insert_order() directly, not through the matching path (that's
Day 3-4, see TASKS.md).
"""

import time

from engine.order_book import OrderBook


def make_order(order_id, side, price, quantity):
    return {
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


def new_book(ring_buffer):
    """Build an OrderBook over a per-test, auto-closed ring buffer.

    Takes the `ring_buffer` fixture (see conftest.py) rather than
    constructing RingBuffer directly, so the buffer's mmap and lock
    handles are released when the test ends.
    """
    return OrderBook(ring_buffer=ring_buffer(capacity=8))


def test_buy_side_sorted_descending_by_price(ring_buffer):
    book = new_book(ring_buffer)
    book.insert_order(make_order(1, "B", 100.0, 10))
    book.insert_order(make_order(2, "B", 102.0, 5))
    book.insert_order(make_order(3, "B", 101.0, 8))

    prices = [o["price"] for o in book.buy_side]
    assert prices == [102.0, 101.0, 100.0]


def test_sell_side_sorted_ascending_by_price(ring_buffer):
    book = new_book(ring_buffer)
    book.insert_order(make_order(1, "S", 105.0, 10))
    book.insert_order(make_order(2, "S", 100.0, 5))
    book.insert_order(make_order(3, "S", 102.5, 8))

    prices = [o["price"] for o in book.sell_side]
    assert prices == [100.0, 102.5, 105.0]


def test_best_bid_and_ask_at_index_zero(ring_buffer):
    book = new_book(ring_buffer)
    book.insert_order(make_order(1, "B", 99.0, 10))
    book.insert_order(make_order(2, "B", 101.0, 10))
    book.insert_order(make_order(3, "S", 103.0, 10))
    book.insert_order(make_order(4, "S", 102.0, 10))

    levels = book.get_top_levels()
    assert levels["bids"][0]["price"] == 101.0
    assert levels["asks"][0]["price"] == 102.0


def test_equal_price_orders_keep_arrival_order(ring_buffer):
    """Time priority at equal price: first in, first out."""
    book = new_book(ring_buffer)
    book.insert_order(make_order(1, "B", 100.0, 10))
    book.insert_order(make_order(2, "B", 100.0, 20))

    ids = [o["order_id"] for o in book.buy_side]
    assert ids == [1, 2]


def test_get_top_levels_respects_depth(ring_buffer):
    book = new_book(ring_buffer)
    for i in range(7):
        book.insert_order(make_order(i, "B", 100.0 + i, 1))

    levels = book.get_top_levels(depth=3)
    assert len(levels["bids"]) == 3
    # depth=3 best bids should be the 3 highest prices: 106, 105, 104
    assert [o["price"] for o in levels["bids"]] == [106.0, 105.0, 104.0]
