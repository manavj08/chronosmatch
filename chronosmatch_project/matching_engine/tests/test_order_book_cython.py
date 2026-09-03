"""
matching_engine/tests/test_order_book_cython.py
---------------------------------------------------
Day 2: tests against the COMPILED Cython extension, not the pure
Python reference (engine/order_book.py). Requires the .pyx to be
built first:

    cd matching_engine
    python setup.py build_ext --inplace

If the .so isn't built yet, these tests fail to import with a clear
ModuleNotFoundError rather than silently falling back to Python ---
that fallback would defeat the point of testing the compiled path.
"""

import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from order_book import OrderBookCython
except ImportError:
    pytest.skip(
        "Cython extension not built. Run: cd matching_engine && "
        "python setup.py build_ext --inplace",
        allow_module_level=True,
    )


def make_order(order_id, side, price, quantity):
    return {
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


def test_extension_is_actually_compiled():
    """Sanity check that we're testing the C-extension, not a .py
    shim --- OrderBookCython should come from a compiled module."""
    import order_book as mod
    assert mod.__file__.endswith((".so", ".pyd"))


def test_buy_side_sorted_descending():
    book = OrderBookCython()
    book.insert_order(make_order(1, "B", 100.0, 10))
    book.insert_order(make_order(2, "B", 102.0, 5))
    book.insert_order(make_order(3, "B", 101.0, 8))

    prices = [o["price"] for o in book.buy_side]
    assert prices == [102.0, 101.0, 100.0]


def test_sell_side_sorted_ascending():
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 105.0, 10))
    book.insert_order(make_order(2, "S", 100.0, 5))
    book.insert_order(make_order(3, "S", 102.5, 8))

    prices = [o["price"] for o in book.sell_side]
    assert prices == [100.0, 102.5, 105.0]


def test_get_top_levels_depth():
    book = OrderBookCython()
    for i in range(7):
        book.insert_order(make_order(i, "B", 100.0 + i, 1))

    levels = book.get_top_levels(depth=3)
    assert len(levels["bids"]) == 3
    assert [o["price"] for o in levels["bids"]] == [106.0, 105.0, 104.0]


def test_matches_pure_python_reference_ordering():
    """Cross-check: the Cython version should produce the same sorted
    order as the pure-Python reference in engine/order_book.py, given
    the same input sequence. Guards against the Cython port silently
    diverging in behavior."""
    from engine.order_book import OrderBook
    from shared.ring_buffer import RingBuffer

    orders = [
        make_order(1, "B", 100.0, 10),
        make_order(2, "B", 103.0, 5),
        make_order(3, "S", 106.0, 7),
        make_order(4, "S", 104.0, 2),
    ]

    cython_book = OrderBookCython()
    for o in orders:
        cython_book.insert_order(o)

    rb = RingBuffer(capacity=8, create=True)
    python_book = OrderBook(ring_buffer=rb)
    for o in orders:
        python_book.insert_order(o)

    cython_bid_prices = [o["price"] for o in cython_book.buy_side]
    python_bid_prices = [o["price"] for o in python_book.buy_side]
    assert cython_bid_prices == python_bid_prices

    cython_ask_prices = [o["price"] for o in cython_book.sell_side]
    python_ask_prices = [o["price"] for o in python_book.sell_side]
    assert cython_ask_prices == python_ask_prices
