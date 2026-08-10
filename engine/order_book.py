"""
engine/order_book.py
---------------------
LEADER'S MATCHING ENGINE.

Day 1: now reads from the REAL shared-memory ring buffer
(shared.ring_buffer.RingBuffer, built by Member A) instead of the old
in-memory fake stub. Every other call site (Member C's dashboard, etc.)
is unaffected, since get_top_levels() / get_last_trade() keep the same
shape.

Day 2: insert_order() now does real sorted insertion by price
(best price first on each side) instead of a plain append. This keeps
get_top_levels() correct without needing to sort on every read, and
sets up O(log n) best-price lookups for Day 3's matching logic.

match_order() is still a placeholder --- real Price-Time Priority
matching lands Day 3-4 (see TASKS.md).
"""

import time
from bisect import insort

from shared.ring_buffer import RingBuffer


class OrderBook:
    def __init__(self, ring_buffer: RingBuffer | None = None):
        # `ring_buffer` is injectable for testing; defaults to a fresh
        # buffer backed by the real shared-memory region.
        self.ring_buffer = ring_buffer or RingBuffer(create=True)

        # Day 2: both sides are kept sorted by price at all times.
        # buy_side:  descending by price (best/highest bid at index 0)
        # sell_side: ascending by price  (best/lowest ask at index 0)
        # Ties broken by arrival order (time priority), since insort
        # is stable relative to equal sort keys and orders are only
        # ever appended, never reordered in place.
        self.buy_side: list[dict] = []   # each item: order dict
        self.sell_side: list[dict] = []
        self.trades: list[dict] = []
        self._trade_id_counter = 1

    # ------------------------------------------------------------------
    # Day 2: real sorted insertion (was a plain append through Day 1).
    # ------------------------------------------------------------------
    def insert_order(self, order: dict) -> None:
        """Insert an order onto the correct side, keeping that side
        sorted by price (best price first). Uses bisect.insort with a
        sort key so this is O(log n) to find the slot, O(n) to shift ---
        fine at this scale; a heap would be the next step if profiling
        ever shows this as a bottleneck (see Day 20: performance pass).
        """
        if order["side"] == "B":
            # Best bid = highest price first -> sort key is negative price
            insort(self.buy_side, order, key=lambda o: -o["price"])
        else:
            # Best ask = lowest price first -> sort key is price as-is
            insort(self.sell_side, order, key=lambda o: o["price"])

    # ------------------------------------------------------------------
    # FAKE / PLACEHOLDER --- replace with real matching (Day 3-4)
    # Sorted insertion (Day 2) is done; this still just inserts, no
    # crossing/matching happens yet.
    # ------------------------------------------------------------------
    def match_order(self, order: dict) -> None:
        """
        Currently does nothing but insert the order (now sorted) --- no
        matching logic yet. Replace with real Price-Time Priority matching:

        1. If order is a Buy: look at the best (lowest) Sell price.
           If Sell price <= Buy price -> trade.
        2. If order is a Sell: look at the best (highest) Buy price.
           If Buy price >= Sell price -> trade.
        3. Trade quantity = min(order.quantity, resting_order.quantity).
        4. Any leftover quantity stays on the book.
        """
        self.insert_order(order)

    def _record_trade(self, buy_order: dict, sell_order: dict, qty: int) -> dict:
        """Helper: build a trade dict in the agreed shared format."""
        trade = {
            "trade_id": self._trade_id_counter,
            "buy_order_id": buy_order["order_id"],
            "sell_order_id": sell_order["order_id"],
            "price": sell_order["price"],
            "quantity": qty,
            "matched_at": time.perf_counter_ns(),
        }
        self._trade_id_counter += 1
        self.trades.append(trade)
        return trade

    # ------------------------------------------------------------------
    # Needed by Member C's dashboard from Day 1 --- keep this working
    # even while the logic above is still fake.
    # ------------------------------------------------------------------
    def get_top_levels(self, depth: int = 5) -> dict:
        """Return the top N price levels on each side. Both lists are
        kept sorted by insert_order() (Day 2), so this is a plain slice
        --- no sorting needed here."""
        return {
            "bids": self.buy_side[:depth],
            "asks": self.sell_side[:depth],
        }

    def get_last_trade(self) -> dict | None:
        return self.trades[-1] if self.trades else None

    # ------------------------------------------------------------------
    # Day 1: now pulls from the REAL shared-memory RingBuffer instead
    # of the old stub. No other call site needed to change.
    # ------------------------------------------------------------------
    def process_next(self) -> dict | None:
        """Pull one order from the real ring buffer and process it."""
        order = self.ring_buffer.read_order()
        if order is None:
            return None
        self.match_order(order)
        return order


if __name__ == "__main__":
    # Manual smoke test against the REAL shared-memory ring buffer.
    book = OrderBook()
    book.ring_buffer.write_order(
        {"order_id": 1, "side": "B", "price": 101.0,
         "quantity": 10, "timestamp": time.perf_counter_ns()}
    )
    book.ring_buffer.write_order(
        {"order_id": 2, "side": "S", "price": 100.5,
         "quantity": 5, "timestamp": time.perf_counter_ns()}
    )

    while True:
        order = book.process_next()
        if order is None:
            break
        print("processed:", order)

    print("top levels:", book.get_top_levels())
