"""
engine/benchmarks/python_baseline_engine.py
-----------------------------------------------
A naive, pure-Python limit order book: plain Python lists of dicts, linear
scan for best price, list.insert() for resting orders, real Price-Time
Priority matching. No Cython, no C structs, no price-level bucketing.

This exists ONLY as the "earlier / unoptimized implementation" reference
point for benchmarks/benchmark_vs_python.py -- it deliberately represents
what a first-pass, un-optimized matching engine looks like, so the Cython
engine's speedup claim is measured against something real, not asserted.
"""

import time


class PythonBaselineOrderBook:
    def __init__(self):
        # Both lists kept sorted by price (best price at index 0);
        # sorting is done with a plain linear insert -- O(n) per insert,
        # not the price-level-bucketed/binary-searched approach the
        # Cython engine uses.
        self.buy_side = []   # sorted descending by price
        self.sell_side = []  # sorted ascending by price
        self.trades = []
        self._trade_id_counter = 1

    def _insert_sorted(self, side_list, order, descending):
        """Naive O(n) linear-scan insert -- no binary search, no price
        levels. This is the operation price-level bucketing in the Cython
        engine specifically targets."""
        i = 0
        if descending:
            while i < len(side_list) and side_list[i]["price"] >= order["price"]:
                i += 1
        else:
            while i < len(side_list) and side_list[i]["price"] <= order["price"]:
                i += 1
        side_list.insert(i, order)

    def insert_order(self, order):
        if order["quantity"] <= 0:
            return
        if order["side"] == "B":
            self._insert_sorted(self.buy_side, order, descending=True)
        else:
            self._insert_sorted(self.sell_side, order, descending=False)

    def match_order(self, order):
        trades = []
        remaining = order["quantity"]
        opposite = self.sell_side if order["side"] == "B" else self.buy_side

        while remaining > 0 and opposite:
            best = opposite[0]
            crosses = (best["price"] <= order["price"]) if order["side"] == "B" \
                else (best["price"] >= order["price"])
            if not crosses:
                break

            fill_qty = min(remaining, best["quantity"])
            now = time.perf_counter_ns()
            entry_ts = order.get("timestamp", now)

            if order["side"] == "B":
                buy_id, sell_id = order["order_id"], best["order_id"]
            else:
                buy_id, sell_id = best["order_id"], order["order_id"]

            trade = {
                "trade_id": self._trade_id_counter,
                "buy_order_id": buy_id,
                "sell_order_id": sell_id,
                "price": best["price"],
                "quantity": fill_qty,
                "entry_timestamp": entry_ts,
                "exit_timestamp": now,
                "latency_ns": now - entry_ts,
            }
            self._trade_id_counter += 1
            self.trades.append(trade)
            trades.append(trade)

            remaining -= fill_qty
            best["quantity"] -= fill_qty
            if best["quantity"] <= 0:
                opposite.pop(0)

        resting = False
        if remaining > 0:
            order = dict(order)
            order["quantity"] = remaining
            self.insert_order(order)
            resting = True

        return {"trades": trades, "resting": resting}

    def get_top_levels(self, depth=5):
        return {"bids": self.buy_side[:depth], "asks": self.sell_side[:depth]}

    def best_bid(self):
        return self.buy_side[0] if self.buy_side else None

    def best_ask(self):
        return self.sell_side[0] if self.sell_side else None
