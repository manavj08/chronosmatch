"""
matching_engine/tests/test_order_book_extras.py
----------------------------------------------------
Follow-up hardening pass: closes gaps found doing a full pass of the
Cython engine against the trading-engine requirement list (Price-Time
Priority order book + Cython optimization + price-level optimization +
GC-safety + latency percentiles + unit test coverage).

Two real gaps were found and are covered here:

1. Order cancellation didn't exist at all. Added OrderBookCython.
   cancel_order(order_id, side) -> bool, implemented as a linear scan
   over the given side's price levels/FIFOs at the C level (no Python
   dict/object involved, nogil-capable) -- see _cancel_c()'s docstring
   in order_book.pyx for the honest O(n) complexity note and why an
   O(1) order_id->location index wasn't built for this.

2. Best bid / best ask / spread were only derivable by calling
   get_top_levels() and reading index 0 of the returned lists -- which
   builds a Python list even when only the single best price is wanted.
   Added best_bid()/best_ask()/spread(), true O(1) (PriceLevel now
   tracks a running total_quantity, maintained on insert/fill/cancel,
   so even the aggregated size at the best price doesn't require
   walking that level's FIFO).

Requires the extension to be built first:
    python setup_demo.py
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
        "Cython extension not built. Run: python setup_demo.py",
        allow_module_level=True,
    )


def make_order(order_id, side, price, quantity):
    return {
        "order_id": order_id, "side": side, "price": price,
        "quantity": quantity, "timestamp": time.perf_counter_ns(),
    }


def new_book():
    return OrderBookCython()


# ----------------------------------------------------------------------
# Order cancellation
# ----------------------------------------------------------------------

def test_cancel_removes_a_resting_order():
    book = new_book()
    book.insert_order(make_order(1, "B", 100.0, 5))

    assert book.cancel_order(1, "B") is True
    assert book.buy_side == []


def test_cancelled_order_no_longer_participates_in_matching():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.cancel_order(1, "S")

    result = book.match_order(make_order(2, "B", 100.0, 5))

    assert result["trades"] == []
    assert result["resting"] is True


def test_cancel_one_of_several_orders_at_the_same_level_preserves_the_rest():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 100.0, 5))
    book.insert_order(make_order(3, "S", 100.0, 5))

    assert book.cancel_order(2, "S") is True

    remaining_ids = [o["order_id"] for o in book.sell_side]
    assert remaining_ids == [1, 3]

    # Time priority among the survivors must be preserved.
    result = book.match_order(make_order(4, "B", 100.0, 5))
    assert result["trades"][0]["sell_order_id"] == 1


def test_cancel_removes_the_price_level_when_it_was_the_only_order():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.cancel_order(1, "S")

    assert book.get_top_levels()["asks"] == []
    assert book.best_ask() is None


def test_cancelling_unknown_order_id_returns_false_and_leaves_book_intact():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))

    assert book.cancel_order(42, "S") is False
    assert len(book.sell_side) == 1


def test_cancel_wrong_side_does_not_find_the_order():
    """An order resting on the sell side must not be cancellable by
    asking for the buy side with the same id."""
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))

    assert book.cancel_order(1, "B") is False
    assert len(book.sell_side) == 1


def test_cancel_on_empty_book_returns_false():
    book = new_book()
    assert book.cancel_order(1, "B") is False


def test_book_still_usable_and_correct_after_many_cancels():
    """Regression-style check: cancel roughly half of a large resting
    population at various price levels, then confirm the book is still
    internally consistent (sorted, correct total resting quantity) and
    still matches correctly afterward."""
    book = new_book()
    for i in range(200):
        book.insert_order(make_order(i, "S", 100.0 + (i % 20), 3))

    for i in range(0, 200, 2):
        assert book.cancel_order(i, "S") is True

    remaining_ids = sorted(o["order_id"] for o in book.sell_side)
    assert remaining_ids == list(range(1, 200, 2))

    prices = [o["price"] for o in book.sell_side]
    assert prices == sorted(prices)

    result = book.match_order(make_order(9999, "B", 200.0, 3))
    assert len(result["trades"]) == 1
    assert result["trades"][0]["sell_order_id"] == 1  # order 0 was cancelled


# ----------------------------------------------------------------------
# Best bid / best ask / spread
# ----------------------------------------------------------------------

def test_best_bid_and_ask_reflect_top_of_book():
    book = new_book()
    book.insert_order(make_order(1, "B", 99.0, 5))
    book.insert_order(make_order(2, "B", 100.0, 3))  # better bid
    book.insert_order(make_order(3, "S", 102.0, 4))
    book.insert_order(make_order(4, "S", 101.0, 6))  # better ask

    assert book.best_bid() == {"price": 100.0, "quantity": 3}
    assert book.best_ask() == {"price": 101.0, "quantity": 6}
    assert book.spread() == 1.0


def test_best_bid_quantity_aggregates_all_orders_at_that_price():
    book = new_book()
    book.insert_order(make_order(1, "B", 100.0, 3))
    book.insert_order(make_order(2, "B", 100.0, 4))

    assert book.best_bid() == {"price": 100.0, "quantity": 7}


def test_best_bid_quantity_updates_after_a_partial_fill():
    """total_quantity is maintained incrementally through matching, not
    just through insert/cancel -- verify a partial fill updates it."""
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 10))

    book.match_order(make_order(2, "B", 100.0, 4))

    assert book.best_ask() == {"price": 100.0, "quantity": 6}


def test_spread_updates_as_top_of_book_changes():
    book = new_book()
    book.insert_order(make_order(1, "B", 99.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))
    assert book.spread() == 2.0

    book.insert_order(make_order(3, "B", 100.0, 5))  # tighter bid
    assert book.spread() == 1.0


def test_spread_none_when_only_one_side_populated():
    book = new_book()
    book.insert_order(make_order(1, "B", 99.0, 5))
    assert book.spread() is None


def test_empty_book_has_no_best_bid_or_ask():
    book = new_book()
    assert book.best_bid() is None
    assert book.best_ask() is None
    assert book.spread() is None
