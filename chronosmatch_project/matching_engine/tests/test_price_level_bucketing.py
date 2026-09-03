"""
matching_engine/tests/test_price_level_bucketing.py
--------------------------------------------------------
Day 10: tests specific to the price-level bucketing rewrite. Day 5's
test_matching.py and Day 6's test_gc_safety.py already cover overall
matching correctness and GC-safety; these tests target the NEW
internal structure directly --- FIFO ordering within a price level,
level creation/removal as orders fill and empty, and the corrected
capacity guard (MAX_PRICE_LEVELS, which a mid-rewrite bug briefly set
too low --- see CHANGELOG.md's Day 10 entry).
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


def test_many_orders_at_same_price_keep_fifo_order():
    """Multiple orders at the exact same price level must match in
    strict arrival order (time priority) --- this is the core
    correctness property the FIFO-per-level design has to preserve."""
    book = OrderBookCython()
    for i in range(5):
        book.insert_order(make_order(i, "S", 100.0, 1))

    matched_order = []
    for _ in range(5):
        result = book.match_order(make_order(999, "B", 100.0, 1))
        matched_order.append(result["trades"][0]["sell_order_id"])

    assert matched_order == [0, 1, 2, 3, 4]


def test_price_level_removed_when_fully_drained():
    """Once every order at a price level is matched away, that level
    should no longer appear in the book at all (not linger as an
    empty entry)."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))

    book.match_order(make_order(3, "B", 100.0, 5))  # fully drains the 100.0 level

    levels = book.get_top_levels()
    prices = [a["price"] for a in levels["asks"]]
    assert 100.0 not in prices
    assert 101.0 in prices


def test_partial_fill_keeps_order_at_front_of_its_level():
    """A partially filled order at the front of a price level's FIFO
    must stay at the front (reduced quantity), not get reordered
    behind later orders at the same price."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 10))
    book.insert_order(make_order(2, "S", 100.0, 10))

    result = book.match_order(make_order(3, "B", 100.0, 4))
    assert result["trades"][0]["sell_order_id"] == 1
    assert result["trades"][0]["quantity"] == 4

    # Order 1 should still be at the front, with 6 remaining, ahead of order 2
    result2 = book.match_order(make_order(4, "B", 100.0, 6))
    assert result2["trades"][0]["sell_order_id"] == 1
    assert result2["trades"][0]["quantity"] == 6

    # Now order 1 is fully drained; order 2 (untouched, still qty 10) is next
    result3 = book.match_order(make_order(5, "B", 100.0, 10))
    assert result3["trades"][0]["sell_order_id"] == 2
    assert result3["trades"][0]["quantity"] == 10


def test_level_reused_after_being_emptied_and_refilled():
    """A price level that's fully drained and later gets a new order
    at that exact price should work correctly --- guards against a
    stale/corrupted level slot after removal."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.match_order(make_order(2, "B", 100.0, 5))  # drains and removes the 100.0 level

    assert 100.0 not in [a["price"] for a in book.get_top_levels()["asks"]]

    book.insert_order(make_order(3, "S", 100.0, 7))
    levels = book.get_top_levels()
    assert levels["asks"][0]["price"] == 100.0
    assert levels["asks"][0]["order_id"] == 3
    assert levels["asks"][0]["quantity"] == 7


def test_many_orders_at_one_level_beyond_initial_fifo_capacity():
    """The per-level FIFO starts small (INITIAL_LEVEL_CAPACITY = 16 in
    the implementation) and must grow via realloc as more orders stack
    up at the same price --- this test deliberately exceeds that
    starting capacity to exercise the growth path."""
    book = OrderBookCython()
    count = 100  # well beyond the initial per-level capacity
    for i in range(count):
        book.insert_order(make_order(i, "S", 100.0, 1))

    # All should still be present and in correct FIFO order
    matched_ids = []
    for _ in range(count):
        result = book.match_order(make_order(9999, "B", 100.0, 1))
        matched_ids.append(result["trades"][0]["sell_order_id"])

    assert matched_ids == list(range(count))


def test_price_level_capacity_matches_day_6_guarantee():
    """Regression test for a real bug found mid-rewrite: an early
    version of this file set MAX_PRICE_LEVELS to 10,000, silently
    dropping orders once a book had more than 10,000 distinct price
    levels (versus Day 6's flat-array design, which supported up to
    MAX_BOOK_DEPTH = 100,000 individual orders/prices). Fixed by
    raising MAX_PRICE_LEVELS to 100,000 to match. This test inserts
    enough distinct prices to have caught the regression."""
    book = OrderBookCython()
    unique_price_count = 99_000  # comfortably beyond the old, too-low cap

    for i in range(unique_price_count):
        book.insert_order(make_order(i, "S", 500.0 - i * 0.001, 1))

    assert len(book.sell_side) == unique_price_count


def test_multi_level_walk_still_correct_with_bucketing():
    """Same scenario as Day 5's test_large_buy_walks_multiple_ask_levels,
    re-verified against the Day 10 internal rewrite specifically ---
    a large incoming order consuming several distinct price levels in
    one call."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 5))
    book.insert_order(make_order(2, "S", 101.0, 5))
    book.insert_order(make_order(3, "S", 102.0, 5))

    result = book.match_order(make_order(4, "B", 102.0, 12))

    assert len(result["trades"]) == 3
    assert [t["price"] for t in result["trades"]] == [100.0, 101.0, 102.0]
    assert [t["quantity"] for t in result["trades"]] == [5, 5, 2]

    remaining = book.get_top_levels()["asks"]
    assert len(remaining) == 1
    assert remaining[0]["order_id"] == 3
    assert remaining[0]["quantity"] == 3


# ----------------------------------------------------------------------
# Day 11: found via deliberate edge-case exploration (zero quantity,
# negative quantity, exact multi-level consumption) rather than from a
# specific spec line --- a genuine bug, not just a coverage exercise.
# ----------------------------------------------------------------------

def test_zero_quantity_order_is_rejected_not_inserted():
    """Regression test for a real bug: a zero-quantity order could
    previously be inserted onto the book and would sit there as a
    phantom price level. When something later matched against it, it
    produced a fake trade with quantity: 0 --- a real execution with
    no economic meaning. Fixed in _insert_c() to reject
    quantity <= 0 orders outright."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 0))

    assert book.sell_side == []
    assert book.get_top_levels()["asks"] == []


def test_negative_quantity_order_is_rejected_not_inserted():
    """Same fix, negative quantity --- shouldn't be reachable through
    normal order generation, but a malformed/malicious order should
    not corrupt book state either."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, -5))

    assert book.sell_side == []


def test_zero_quantity_resting_order_cannot_produce_phantom_trade():
    """End-to-end regression check: even if a zero-quantity order
    somehow made it onto the book in the past (the bug above), a
    later incoming order matching at that price level must still only
    trade against the real, positive-quantity order behind it --- not
    produce a zero-quantity trade first. With the _insert_c() fix,
    the zero-quantity order is never inserted at all, so this
    verifies the end result: only the real order gets matched."""
    book = OrderBookCython()
    book.insert_order(make_order(1, "S", 100.0, 0))   # rejected, never on the book
    book.insert_order(make_order(2, "S", 100.0, 10))  # the only real order at this price

    result = book.match_order(make_order(3, "B", 100.0, 10))

    assert len(result["trades"]) == 1
    assert result["trades"][0]["sell_order_id"] == 2
    assert result["trades"][0]["quantity"] == 10


def test_exact_multi_level_consumption_leaves_book_empty():
    """Edge case found during exploration: an incoming order whose
    quantity exactly equals the sum of several resting price levels
    should consume all of them and leave nothing resting --- verifies
    no off-by-one leaves a phantom empty level or an incorrectly
    resting remainder of 0."""
    book = OrderBookCython()
    for i in range(5):
        book.insert_order(make_order(i, "S", 100.0 + i, 10))

    result = book.match_order(make_order(99, "B", 104.0, 50))  # exactly 5 * 10

    assert len(result["trades"]) == 5
    assert result["resting"] is False
    assert book.get_top_levels() == {"bids": [], "asks": []}
    assert book.sell_side == []
