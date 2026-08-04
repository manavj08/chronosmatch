"""
order_book.py
-------------
LEADER'S STARTER SKELETON.

This is the shell for the matching engine. Method bodies are either
empty (`pass`) or contain the simplest possible fake logic, so the
class can be imported and run immediately by teammates (Member C
needs get_top_levels() to exist right away for the dashboard).

YOUR JOB (Leader): fill in the real logic step by step:
    Day 2 -> implement insert_order() properly (sorted by price)
    Day 3 -> implement match_order() (Price-Time Priority)
    Day 4 -> swap read_order() calls from stub to real buffer
    Day 6 -> add timestamp capture for latency
"""

import time

from shared_interface import read_order


class OrderBook:
    def __init__(self):
        # FAKE for now: plain lists. Later: keep sorted by price for
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
    # FAKE / PLACEHOLDER --- replace with real matching (Day 3)
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
    # Runs against the STUB buffer today. Day 4: no changes needed here
    # since it already calls read_order() from shared_interface --- Member
    # A just swaps what *inside* read_order(), not this call site.
    # ------------------------------------------------------------------
    def process_next(self) -> dict | None:
        """Pull one order from the bus and process it."""
        order = read_order()
        if order is None:
            return None
        self.match_order(order)
        return order


if __name__ == "__main__":
    # Quick manual smoke test using the stub buffer directly.
    from shared_interface import write_order, next_order_id

    book = OrderBook()
    write_order({"order_id": next_order_id(), "side": "B", "price": 101.0,
                 "quantity": 10, "timestamp": time.perf_counter_ns()})
    write_order({"order_id": next_order_id(), "side": "S", "price": 100.5,
                 "quantity": 5, "timestamp": time.perf_counter_ns()})

    while True:
        order = book.process_next()
        if order is None:
            break
        print("processed:", order)

    print("top levels:", book.get_top_levels())
