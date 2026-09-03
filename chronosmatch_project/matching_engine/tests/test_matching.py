"""
matching_engine/tests/test_matching.py
-----------------------------------------
Day 5: tests for real Price-Time Priority matching (crossing) in the
Cython engine --- OrderBookCython.match_order(). This is the actual
spec deliverable ("Prove the Order Book correctly matches a Buy order
with a corresponding Sell order instantly" — Mid-Project Review,
Day 9 formalizes this further).

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
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


def new_book():
    return OrderBookCython()


# ----------------------------------------------------------------------
# Full match
# ----------------------------------------------------------------------

def test_incoming_buy_fully_matches_resting_sell_same_quantity():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 10))

    result = book.match_order(make_order(2, "B", 100.0, 10))

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["buy_order_id"] == 2
    assert trade["sell_order_id"] == 1
    assert trade["quantity"] == 10
    assert trade["price"] == 100.0  # trade executes at the resting order's price
    assert result["resting"] is False
    assert book.get_top_levels()["asks"] == []
    assert book.get_top_levels()["bids"] == []


def test_incoming_sell_fully_matches_resting_buy():
    book = new_book()
    book.insert_order(make_order(1, "B", 105.0, 8))

    result = book.match_order(make_order(2, "S", 105.0, 8))

    assert len(result["trades"]) == 1
    trade = result["trades"][0]
    assert trade["buy_order_id"] == 1
    assert trade["sell_order_id"] == 2
    assert trade["quantity"] == 8
    assert result["resting"] is False
    assert book.get_top_levels()["bids"] == []


def test_buy_matches_at_better_price_than_offered():
    """Incoming buy willing to pay 105, resting ask only wants 100 ---
    should match (trade executes at the resting/better price, not the
    incoming order's price)."""
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))

    result = book.match_order(make_order(2, "B", 105.0, 5))

    assert len(result["trades"]) == 1
    assert result["trades"][0]["price"] == 100.0


# ----------------------------------------------------------------------
# Partial match
# ----------------------------------------------------------------------

def test_incoming_buy_partially_fills_larger_resting_sell():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 20))

    result = book.match_order(make_order(2, "B", 100.0, 6))

    assert len(result["trades"]) == 1
    assert result["trades"][0]["quantity"] == 6
    assert result["resting"] is False  # incoming buy fully consumed

    remaining_asks = book.get_top_levels()["asks"]
    assert len(remaining_asks) == 1
    assert remaining_asks[0]["order_id"] == 1
    assert remaining_asks[0]["quantity"] == 14  # 20 - 6


def test_incoming_sell_larger_than_resting_buy_rests_remainder():
    book = new_book()
    book.insert_order(make_order(1, "B", 100.0, 5))

    result = book.match_order(make_order(2, "S", 99.0, 8))

    assert len(result["trades"]) == 1
    assert result["trades"][0]["quantity"] == 5
    assert result["resting"] is True  # 3 units of the sell order rest

    remaining_asks = book.get_top_levels()["asks"]
    assert len(remaining_asks) == 1
    assert remaining_asks[0]["order_id"] == 2
    assert remaining_asks[0]["quantity"] == 3
    assert book.get_top_levels()["bids"] == []


# ----------------------------------------------------------------------
# Multi-level matching (walks the book across several price levels)
# ----------------------------------------------------------------------

def test_large_buy_walks_multiple_ask_levels():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))
    book.insert_order(make_order(3, "S", 102.0, 5))

    # Willing to pay up to 102, wants 12 total -> consumes levels 100, 101
    # fully (5+5=10) and takes 2 from the 102 level
    result = book.match_order(make_order(4, "B", 102.0, 12))

    assert len(result["trades"]) == 3
    prices_filled = [t["price"] for t in result["trades"]]
    assert prices_filled == [100.0, 101.0, 102.0]
    quantities = [t["quantity"] for t in result["trades"]]
    assert quantities == [5, 5, 2]

    remaining_asks = book.get_top_levels()["asks"]
    assert len(remaining_asks) == 1
    assert remaining_asks[0]["order_id"] == 3
    assert remaining_asks[0]["quantity"] == 3


def test_large_buy_stops_at_price_limit_even_with_more_asks_available():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 110.0, 5))  # too expensive

    result = book.match_order(make_order(3, "B", 105.0, 10))

    # Only the 100.0 level crosses; 110.0 is above the buy's limit
    assert len(result["trades"]) == 1
    assert result["trades"][0]["price"] == 100.0
    assert result["resting"] is True  # 5 units rest, waiting for a lower ask

    remaining_bids = book.get_top_levels()["bids"]
    assert len(remaining_bids) == 1
    assert remaining_bids[0]["quantity"] == 5


# ----------------------------------------------------------------------
# No match
# ----------------------------------------------------------------------

def test_no_cross_both_orders_rest():
    book = new_book()
    book.insert_order(make_order(1, "S", 105.0, 10))

    result = book.match_order(make_order(2, "B", 100.0, 10))

    assert result["trades"] == []
    assert result["resting"] is True
    assert len(book.get_top_levels()["bids"]) == 1
    assert len(book.get_top_levels()["asks"]) == 1


def test_match_against_empty_book_rests_entirely():
    book = new_book()
    result = book.match_order(make_order(1, "B", 100.0, 10))

    assert result["trades"] == []
    assert result["resting"] is True
    assert book.get_top_levels()["bids"][0]["order_id"] == 1


# ----------------------------------------------------------------------
# Time priority: same price, first order in should be matched first
# ----------------------------------------------------------------------

def test_time_priority_at_equal_price():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))  # arrived first
    book.insert_order(make_order(2, "S", 100.0, 5))  # arrived second

    result = book.match_order(make_order(3, "B", 100.0, 5))

    assert len(result["trades"]) == 1
    assert result["trades"][0]["sell_order_id"] == 1  # first-in matched first

    remaining_asks = book.get_top_levels()["asks"]
    assert len(remaining_asks) == 1
    assert remaining_asks[0]["order_id"] == 2  # second order untouched


# ----------------------------------------------------------------------
# Trade bookkeeping
# ----------------------------------------------------------------------

def test_trade_ids_increment_across_multiple_matches():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))

    book.match_order(make_order(3, "B", 100.0, 5))
    result2 = book.match_order(make_order(4, "B", 101.0, 5))

    assert result2["trades"][0]["trade_id"] == 2
    assert book.get_last_trade()["trade_id"] == 2


def test_get_last_trade_reflects_most_recent():
    book = new_book()
    book.insert_order(make_order(1, "S", 100.0, 10))

    assert book.get_last_trade() is None  # no trades yet

    book.match_order(make_order(2, "B", 100.0, 4))
    first_last = book.get_last_trade()
    assert first_last["quantity"] == 4

    book.match_order(make_order(3, "B", 100.0, 6))
    second_last = book.get_last_trade()
    assert second_last["quantity"] == 6
    assert second_last["trade_id"] > first_last["trade_id"]
