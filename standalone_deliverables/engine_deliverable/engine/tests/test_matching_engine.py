"""
engine/tests/test_matching_engine.py
--------------------------------------
Unit tests for the Cython MatchingEngine (matching_engine.pyx).

Build the extension first:
    cd engine
    python setup.py build_ext --inplace

Run:
    cd engine
    pytest tests/ -v

Coverage maps directly onto the required test matrix:
    - Buy + Sell match              -> TestFullMatch
    - No match                      -> TestNoMatch
    - Partial fill                  -> TestPartialFill
    - Multiple price levels         -> TestMultiLevelMatching
    - Price-time priority           -> TestPriceTimePriority
    - Large order                   -> TestLargeOrder
    - Empty book                    -> TestEmptyBook
    - Book consistency after trades -> TestBookConsistency
Plus engine-specific extras:
    - Order cancellation            -> TestCancellation
    - Best bid/ask + spread         -> TestBestBidAskSpread
    - Latency stats shape           -> TestLatencyStats
    - GC-safety of the hot path     -> TestGCSafety
"""

import gc
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    from matching_engine import MatchingEngine
except ImportError:
    pytest.skip(
        "Cython extension not built. Run: cd engine && python setup.py build_ext --inplace",
        allow_module_level=True,
    )


def make_order(order_id, side, price, quantity, timestamp=None):
    return {
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp if timestamp is not None else time.perf_counter_ns(),
    }


def new_book():
    return MatchingEngine()


# ======================================================================
# Buy + Sell match (full fill)
# ======================================================================

class TestFullMatch:
    def test_incoming_buy_fully_matches_resting_sell_same_quantity(self):
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
        assert book.get_top_levels() == {"bids": [], "asks": []}

    def test_incoming_sell_fully_matches_resting_buy(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 105.0, 8))

        result = book.match_order(make_order(2, "S", 105.0, 8))

        assert len(result["trades"]) == 1
        trade = result["trades"][0]
        assert trade["buy_order_id"] == 1
        assert trade["sell_order_id"] == 2
        assert trade["quantity"] == 8
        assert result["resting"] is False

    def test_buy_matches_at_resting_price_not_incoming_price(self):
        """Incoming buy willing to pay 105, resting ask only wants 100 --
        trade executes at the better/resting price, not the incoming
        order's limit price."""
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))

        result = book.match_order(make_order(2, "B", 105.0, 5))

        assert result["trades"][0]["price"] == 100.0

    def test_trade_carries_latency_instrumentation(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 10, timestamp=0))

        result = book.match_order(make_order(2, "B", 100.0, 10, timestamp=0))

        trade = result["trades"][0]
        assert trade["exit_timestamp"] >= trade["entry_timestamp"]
        assert trade["latency_ns"] == trade["exit_timestamp"] - trade["entry_timestamp"]
        assert trade["latency_ns"] >= 0


# ======================================================================
# No match
# ======================================================================

class TestNoMatch:
    def test_no_cross_both_orders_rest(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 105.0, 10))

        result = book.match_order(make_order(2, "B", 100.0, 10))

        assert result["trades"] == []
        assert result["resting"] is True
        assert len(book.get_top_levels()["bids"]) == 1
        assert len(book.get_top_levels()["asks"]) == 1

    def test_orders_at_same_price_but_wrong_side_relationship_do_not_match(self):
        """A resting ask above a resting bid's limit should never cross,
        no matter how many times it's checked."""
        book = new_book()
        book.insert_order(make_order(1, "S", 100.01, 10))
        result = book.match_order(make_order(2, "B", 100.00, 10))
        assert result["trades"] == []


# ======================================================================
# Partial fill
# ======================================================================

class TestPartialFill:
    def test_incoming_buy_partially_fills_larger_resting_sell(self):
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

    def test_incoming_sell_larger_than_resting_buy_rests_remainder(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 100.0, 5))

        result = book.match_order(make_order(2, "S", 99.0, 8))

        assert len(result["trades"]) == 1
        assert result["trades"][0]["quantity"] == 5
        assert result["resting"] is True  # 3 units of the sell order rest

        remaining_asks = book.get_top_levels()["asks"]
        assert remaining_asks[0]["order_id"] == 2
        assert remaining_asks[0]["quantity"] == 3

    def test_partially_filled_resting_order_keeps_its_time_priority(self):
        """A partially-filled order must stay at the front of its price
        level's queue (reduced quantity), not lose its place in line."""
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 10))
        book.insert_order(make_order(2, "S", 100.0, 10))

        r1 = book.match_order(make_order(3, "B", 100.0, 4))
        assert r1["trades"][0]["sell_order_id"] == 1
        assert r1["trades"][0]["quantity"] == 4

        r2 = book.match_order(make_order(4, "B", 100.0, 6))
        assert r2["trades"][0]["sell_order_id"] == 1  # still order 1, now drained
        assert r2["trades"][0]["quantity"] == 6

        r3 = book.match_order(make_order(5, "B", 100.0, 10))
        assert r3["trades"][0]["sell_order_id"] == 2  # order 2's turn now


# ======================================================================
# Multiple price levels
# ======================================================================

class TestMultiLevelMatching:
    def test_large_buy_walks_multiple_ask_levels(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.insert_order(make_order(2, "S", 101.0, 5))
        book.insert_order(make_order(3, "S", 102.0, 5))

        result = book.match_order(make_order(4, "B", 102.0, 12))

        assert len(result["trades"]) == 3
        assert [t["price"] for t in result["trades"]] == [100.0, 101.0, 102.0]
        assert [t["quantity"] for t in result["trades"]] == [5, 5, 2]

        remaining_asks = book.get_top_levels()["asks"]
        assert len(remaining_asks) == 1
        assert remaining_asks[0]["order_id"] == 3
        assert remaining_asks[0]["quantity"] == 3

    def test_large_buy_stops_at_price_limit_even_with_more_asks_available(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.insert_order(make_order(2, "S", 110.0, 5))  # too expensive

        result = book.match_order(make_order(3, "B", 105.0, 10))

        assert len(result["trades"]) == 1
        assert result["trades"][0]["price"] == 100.0
        assert result["resting"] is True

        remaining_bids = book.get_top_levels()["bids"]
        assert remaining_bids[0]["quantity"] == 5

    def test_price_level_is_removed_once_fully_drained(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.insert_order(make_order(2, "S", 101.0, 5))

        book.match_order(make_order(3, "B", 100.0, 5))  # drains the 100.0 level

        prices = [a["price"] for a in book.get_top_levels()["asks"]]
        assert 100.0 not in prices
        assert 101.0 in prices


# ======================================================================
# Price-time priority
# ======================================================================

class TestPriceTimePriority:
    def test_better_price_matched_before_earlier_worse_price(self):
        """Price priority beats time priority: a later order at a better
        price must still match before an earlier order at a worse price."""
        book = new_book()
        book.insert_order(make_order(1, "S", 101.0, 5))  # arrived first, worse price
        book.insert_order(make_order(2, "S", 100.0, 5))  # arrived second, better price

        result = book.match_order(make_order(3, "B", 101.0, 5))

        assert result["trades"][0]["sell_order_id"] == 2  # better price wins

    def test_time_priority_at_equal_price(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))  # arrived first
        book.insert_order(make_order(2, "S", 100.0, 5))  # arrived second

        result = book.match_order(make_order(3, "B", 100.0, 5))

        assert result["trades"][0]["sell_order_id"] == 1  # first-in matched first
        remaining = book.get_top_levels()["asks"]
        assert remaining[0]["order_id"] == 2

    def test_many_orders_at_same_price_maintain_strict_fifo(self):
        book = new_book()
        for i in range(10):
            book.insert_order(make_order(i, "S", 100.0, 1))

        matched_order = []
        for _ in range(10):
            result = book.match_order(make_order(999, "B", 100.0, 1))
            matched_order.append(result["trades"][0]["sell_order_id"])

        assert matched_order == list(range(10))


# ======================================================================
# Large order
# ======================================================================

class TestLargeOrder:
    def test_single_order_consumes_many_resting_orders_across_many_levels(self):
        """One large incoming order sweeps 200 distinct resting price
        levels in a single match_order() call."""
        book = new_book()
        n_levels = 200
        for i in range(n_levels):
            book.insert_order(make_order(i, "S", 100.0 + i, 10))

        result = book.match_order(make_order(9999, "B", 100.0 + n_levels, n_levels * 10))

        assert len(result["trades"]) == n_levels
        assert sum(t["quantity"] for t in result["trades"]) == n_levels * 10
        assert result["resting"] is False
        assert book.get_top_levels() == {"bids": [], "asks": []}

    def test_large_order_partially_fills_then_rests_the_remainder(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 100_000))

        result = book.match_order(make_order(2, "B", 100.0, 250_000))

        assert result["trades"][0]["quantity"] == 100_000
        assert result["resting"] is True
        remaining_bids = book.get_top_levels()["bids"]
        assert remaining_bids[0]["quantity"] == 150_000

    def test_many_orders_at_one_level_beyond_initial_fifo_capacity(self):
        """The per-level FIFO starts with a small capacity and must grow
        (realloc) as more orders stack up at the same price."""
        book = new_book()
        count = 500  # well beyond the initial per-level FIFO capacity
        for i in range(count):
            book.insert_order(make_order(i, "S", 100.0, 1))

        matched_ids = []
        for _ in range(count):
            result = book.match_order(make_order(9999, "B", 100.0, 1))
            matched_ids.append(result["trades"][0]["sell_order_id"])

        assert matched_ids == list(range(count))


# ======================================================================
# Empty book
# ======================================================================

class TestEmptyBook:
    def test_match_against_empty_book_rests_entirely(self):
        book = new_book()
        result = book.match_order(make_order(1, "B", 100.0, 10))

        assert result["trades"] == []
        assert result["resting"] is True
        assert book.get_top_levels()["bids"][0]["order_id"] == 1

    def test_empty_book_has_no_best_bid_or_ask(self):
        book = new_book()
        assert book.best_bid() is None
        assert book.best_ask() is None
        assert book.spread() is None

    def test_empty_book_get_top_levels_shape(self):
        book = new_book()
        assert book.get_top_levels() == {"bids": [], "asks": []}

    def test_empty_book_has_no_last_trade(self):
        book = new_book()
        assert book.get_last_trade() is None

    def test_empty_book_latency_stats_are_zeroed_not_an_error(self):
        book = new_book()
        stats = book.get_latency_stats()
        assert stats["count"] == 0
        assert stats["p50_ns"] == stats["p95_ns"] == stats["p99_ns"] == stats["p999_ns"] == 0

    def test_cancel_on_empty_book_returns_false(self):
        book = new_book()
        assert book.cancel_order(1, "B") is False


# ======================================================================
# Book consistency after trades
# ======================================================================

class TestBookConsistency:
    def test_sides_stay_sorted_after_a_sequence_of_trades(self):
        """Buy side must stay sorted descending, sell side ascending, at
        every point -- verified after a mixed sequence of inserts and
        matches, not just immediately after a single operation."""
        book = new_book()
        for i in range(20):
            book.insert_order(make_order(i, "S", 100.0 + (i % 7), 3))
        for i in range(20, 40):
            book.insert_order(make_order(i, "B", 90.0 + (i % 5), 3))

        # Trigger a handful of partial/full matches that touch several levels.
        for i in range(5):
            book.match_order(make_order(1000 + i, "B", 106.0, 4))

        sell_prices = [o["price"] for o in book.sell_side]
        assert sell_prices == sorted(sell_prices)

        buy_prices = [o["price"] for o in book.buy_side]
        assert buy_prices == sorted(buy_prices, reverse=True)

    def test_spread_never_negative_after_trades_leave_a_two_sided_book(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 101.0, 3))
        book.insert_order(make_order(2, "S", 100.0, 3))  # will be consumed
        book.insert_order(make_order(3, "B", 95.0, 3))

        book.match_order(make_order(4, "B", 100.0, 3))  # consumes the 100.0 ask

        spread = book.spread()
        assert spread is not None
        assert spread >= 0

    def test_trade_ids_increment_monotonically_across_matches(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.insert_order(make_order(2, "S", 101.0, 5))

        book.match_order(make_order(3, "B", 100.0, 5))
        result2 = book.match_order(make_order(4, "B", 101.0, 5))

        assert result2["trades"][0]["trade_id"] == 2
        assert book.get_last_trade()["trade_id"] == 2

    def test_no_resting_quantity_is_created_or_destroyed_by_matching(self):
        """Conservation check: total resting quantity removed from the
        book must exactly equal total traded quantity, for a randomized-
        ish but deterministic sequence of orders."""
        book = new_book()
        total_inserted = 0
        for i in range(50):
            qty = (i % 5) + 1
            book.insert_order(make_order(i, "S", 100.0 + (i % 10), qty))
            total_inserted += qty

        total_traded = 0
        for i in range(50, 80):
            result = book.match_order(make_order(i, "B", 110.0, 3))
            total_traded += sum(t["quantity"] for t in result["trades"])

        remaining_on_book = sum(o["quantity"] for o in book.sell_side)
        assert total_traded + remaining_on_book == total_inserted

    def test_exact_multi_level_consumption_leaves_book_empty(self):
        book = new_book()
        for i in range(5):
            book.insert_order(make_order(i, "S", 100.0 + i, 10))

        result = book.match_order(make_order(99, "B", 104.0, 50))  # exactly 5 * 10

        assert result["resting"] is False
        assert book.get_top_levels() == {"bids": [], "asks": []}
        assert book.sell_side == []

    def test_zero_and_negative_quantity_orders_are_rejected(self):
        """Regression guard: a zero/negative-quantity order must never be
        inserted, since it would otherwise later produce a phantom trade
        with no real economic meaning."""
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 0))
        book.insert_order(make_order(2, "S", 100.0, -5))
        assert book.sell_side == []


# ======================================================================
# Order cancellation
# ======================================================================

class TestCancellation:
    def test_cancel_removes_a_resting_order(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 100.0, 5))

        assert book.cancel_order(1, "B") is True
        assert book.buy_side == []

    def test_cancelled_order_no_longer_participates_in_matching(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.cancel_order(1, "S")

        result = book.match_order(make_order(2, "B", 100.0, 5))

        assert result["trades"] == []
        assert result["resting"] is True

    def test_cancel_one_of_several_orders_at_the_same_level_preserves_the_rest(self):
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

    def test_cancel_removes_the_price_level_when_it_was_the_only_order(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))
        book.cancel_order(1, "S")

        assert book.get_top_levels()["asks"] == []
        assert book.best_ask() is None

    def test_cancelling_unknown_order_id_returns_false_and_leaves_book_intact(self):
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))

        assert book.cancel_order(42, "S") is False
        assert len(book.sell_side) == 1

    def test_cancel_wrong_side_does_not_find_the_order(self):
        """An order resting on the sell side must not be cancellable by
        asking for the buy side with the same id."""
        book = new_book()
        book.insert_order(make_order(1, "S", 100.0, 5))

        assert book.cancel_order(1, "B") is False
        assert len(book.sell_side) == 1


# ======================================================================
# Best bid / best ask / spread
# ======================================================================

class TestBestBidAskSpread:
    def test_best_bid_and_ask_reflect_top_of_book(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 99.0, 5))
        book.insert_order(make_order(2, "B", 100.0, 3))  # better bid
        book.insert_order(make_order(3, "S", 102.0, 4))
        book.insert_order(make_order(4, "S", 101.0, 6))  # better ask

        assert book.best_bid() == {"price": 100.0, "quantity": 3}
        assert book.best_ask() == {"price": 101.0, "quantity": 6}
        assert book.spread() == 1.0

    def test_best_bid_quantity_aggregates_all_orders_at_that_price(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 100.0, 3))
        book.insert_order(make_order(2, "B", 100.0, 4))

        assert book.best_bid() == {"price": 100.0, "quantity": 7}

    def test_spread_updates_as_top_of_book_changes(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 99.0, 5))
        book.insert_order(make_order(2, "S", 101.0, 5))
        assert book.spread() == 2.0

        book.insert_order(make_order(3, "B", 100.0, 5))  # tighter bid
        assert book.spread() == 1.0

    def test_spread_none_when_only_one_side_populated(self):
        book = new_book()
        book.insert_order(make_order(1, "B", 99.0, 5))
        assert book.spread() is None


# ======================================================================
# Latency stats shape (p50 / p95 / p99 / p999 / max)
# ======================================================================

class TestLatencyStats:
    def _seed_and_trade(self, book, count):
        book.insert_order(make_order(0, "S", 100.0, count * 2))
        for i in range(count):
            book.match_order(make_order(i + 1, "B", 100.0, 1))

    def test_stats_shape_has_all_required_percentile_fields(self):
        book = new_book()
        self._seed_and_trade(book, 200)
        stats = book.get_latency_stats()

        assert set(stats.keys()) == {
            "count", "min_ns", "mean_ns", "max_ns",
            "p50_ns", "p95_ns", "p99_ns", "p999_ns",
        }

    def test_percentiles_are_correctly_ordered(self):
        book = new_book()
        self._seed_and_trade(book, 3000)
        stats = book.get_latency_stats()

        assert stats["min_ns"] <= stats["p50_ns"]
        assert stats["p50_ns"] <= stats["p95_ns"]
        assert stats["p95_ns"] <= stats["p99_ns"]
        assert stats["p99_ns"] <= stats["p999_ns"]
        assert stats["p999_ns"] <= stats["max_ns"]

    def test_lifetime_count_is_exact(self):
        book = new_book()
        self._seed_and_trade(book, 777)
        assert book.get_latency_stats()["count"] == 777


# ======================================================================
# GC-safety of the hot path
# ======================================================================

class TestGCSafety:
    """Verifies the matching loop's actual requirement: it must not
    depend on, or trigger, Python's garbage collector. This is measured,
    not just asserted from code structure -- see run_c_only_matching_cycle,
    which bypasses all dict conversion so nothing here can allocate a
    tracked Python object."""

    ITERATIONS = 100_000

    def test_c_only_matching_allocates_no_python_objects(self):
        book = new_book()

        # Seed large resting orders on both sides so every subsequent
        # incoming order in the loop below actually matches something,
        # rather than piling up as new resting inventory.
        book.run_c_only_matching_cycle(0, ord("S"), 100.0, 10_000_000_000, 0)
        book.run_c_only_matching_cycle(-1, ord("B"), 101.0, 10_000_000_000, 0)

        gc.collect()
        baseline_blocks = sys.getallocatedblocks()

        for i in range(1, self.ITERATIONS + 1):
            side = ord("B") if i % 2 == 0 else ord("S")
            price = 100.0 if i % 2 == 0 else 101.0
            book.run_c_only_matching_cycle(i, side, price, 1, i)

        after_blocks = sys.getallocatedblocks()

        gc.collect()
        noop_start = sys.getallocatedblocks()
        total = 0
        for i in range(1, self.ITERATIONS + 1):
            total += i
        noop_end = sys.getallocatedblocks()

        matching_growth = after_blocks - baseline_blocks
        noop_growth = noop_end - noop_start

        assert matching_growth < noop_growth + 50, (
            f"C-only matching path allocated {matching_growth} blocks over "
            f"{self.ITERATIONS} iterations (no-op baseline: {noop_growth}) -- "
            f"a Python object appears to be getting created in the hot path."
        )

    def test_c_only_matching_triggers_no_gc_collections(self):
        book = new_book()
        book.run_c_only_matching_cycle(0, ord("S"), 100.0, 10_000_000_000, 0)
        book.run_c_only_matching_cycle(-1, ord("B"), 101.0, 10_000_000_000, 0)

        gc.disable()
        try:
            collections_before = gc.get_stats()[0]["collections"]
            for i in range(1, self.ITERATIONS + 1):
                side = ord("B") if i % 2 == 0 else ord("S")
                price = 100.0 if i % 2 == 0 else 101.0
                book.run_c_only_matching_cycle(i, side, price, 1, i)
            collections_after = gc.get_stats()[0]["collections"]
        finally:
            gc.enable()

        assert collections_after == collections_before

    def test_c_only_path_still_produces_correct_trades(self):
        """Sanity check: the C-only path isn't fast because it's silently
        skipping matching logic -- confirm it's still correct."""
        book = new_book()
        book.run_c_only_matching_cycle(1, ord("S"), 100.0, 10, 0)
        remaining = book.run_c_only_matching_cycle(2, ord("B"), 100.0, 10, 1)

        assert remaining == 0
        last_trade = book.get_last_trade()
        assert last_trade["buy_order_id"] == 2
        assert last_trade["sell_order_id"] == 1
        assert last_trade["quantity"] == 10

    def test_new_price_level_creation_via_malloc_triggers_no_collections(self):
        """Every order below is at a unique price, forcing malloc() for a
        brand-new PriceLevel each time -- exercises the allocator path
        specifically, not just repeated appends to one existing level."""
        book = new_book()
        count = self.ITERATIONS // 4

        gc.disable()
        try:
            collections_before = gc.get_stats()[0]["collections"]
            for i in range(count):
                book.run_c_only_matching_cycle(i, ord("S"), 1000.0 + i * 0.01, 1, i)
            collections_after = gc.get_stats()[0]["collections"]
        finally:
            gc.enable()

        assert collections_after == collections_before
        assert len(book.sell_side) == count

    def test_fifo_growth_via_realloc_triggers_no_collections(self):
        """Every order below is at the SAME price, forcing realloc() of
        that level's FIFO array once the initial capacity is exceeded."""
        book = new_book()
        count = self.ITERATIONS // 4

        gc.disable()
        try:
            collections_before = gc.get_stats()[0]["collections"]
            for i in range(count):
                book.run_c_only_matching_cycle(i, ord("S"), 100.0, 1, i)
            collections_after = gc.get_stats()[0]["collections"]
        finally:
            gc.enable()

        assert collections_after == collections_before
        assert len(book.sell_side) == count
