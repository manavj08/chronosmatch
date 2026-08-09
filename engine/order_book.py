"""
engine/order_book.py
---------------------
LEADER'S MATCHING ENGINE.

Day 1 change: this now reads from the REAL shared-memory ring buffer
(shared.ring_buffer.RingBuffer, built by Member A) instead of the old
in-memory fake stub. Every other call site (Member C's dashboard, etc.)
is unaffected, since get_top_levels() / get_last_trade() keep the same
shape.

insert_order() and match_order() are still placeholders --- real
Price-Time Priority matching lands Day 2-4 (see TASKS.md).
"""

import time

from shared.ring_buffer import RingBuffer


class OrderBook:
    def __init__(self, ring_buffer: RingBuffer | None = None):
        # `ring_buffer` is injectable for testing; defaults to a fresh
        # buffer backed by the real shared-memory region.
        self.ring_buffer = ring_buffer or RingBuffer(create=True)

        # FAKE for now: plain lists. Day 2: keep sorted by price for
        # O(log n) best-price lookups instead of O(n) scans.
        self.buy_side: list[dict] = []   # each item: order dict
        self.sell_side: list[dict] = []
        self.trades: list[dict] = []
        self._trade_id_counter = 1

    # ------------------------------------------------------------------
    # FAKE / PLACEHOLDER --- replace with real sorted insertion (Day 2)
    # ------------------------------------------------------------------
    def insert_order(self, order: dict) -> None:
        """Add an order to the correct side. Currently just appends ---
        no price sorting yet. Replace with sorted insertion."""
        if order["side"] == "B":
            self.buy_side.append(order)
        else:
            self.sell_side.append(order)

    # ------------------------------------------------------------------
    # FAKE / PLACEHOLDER --- replace with real matching (Day 3-4)
    # ------------------------------------------------------------------
    def match_order(self, order: dict) -> None:
        """
        Currently does nothing but insert the order --- no matching logic
        yet. Replace with real Price-Time Priority matching:

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
        """Return the top N price levels on each side.
        FAKE for now: just returns whatever is in the lists, unsorted."""
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
