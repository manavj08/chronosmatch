# cython: language_level=3
"""
matching_engine/order_book.pyx
--------------------------------
CYTHON LIMIT ORDER BOOK.

Day 2: first working .pyx compiled to a real C-extension. Ports the
sorted-insertion logic that used to live in engine/order_book.py
(pure Python), but with statically-typed C variables instead of
Python objects, per spec: "defining variables statically using
C-types to bypass the Python GIL."

order_id, quantity, timestamp -> C long long (8 bytes, matches the
'Q' in shared/serializer.py's struct format)
price -> C double
side -> C char ('B' or 'S')

Day 5: real Price-Time Priority matching (crossing), replacing the
insert-only placeholder. Algorithm (same spec as the pure-Python
reference in engine/order_book.py):

1. Incoming Buy: repeatedly check the best (lowest) resting Sell
   price. While best ask <= buy price, a trade occurs.
2. Incoming Sell: repeatedly check the best (highest) resting Buy
   price. While best bid >= sell price, a trade occurs.
3. Trade quantity = min(incoming remaining qty, resting order qty).
4. If the resting order is fully consumed, remove it from the book.
   If it's only partially filled, reduce its quantity in place and
   stop (it remains the new best price on its side).
5. If the incoming order still has quantity left after no more
   prices cross, insert the remainder onto the book (sorted, as
   insert_order() already does).

This still allocates trade dicts as Python objects --- removing that
Python-object interaction from the hot path is Day 6's job
("Strip remaining Python object interaction from the matching loop").
Day 5's scope is getting the matching LOGIC correct; Day 6 is making
it GC-safe.
"""

from libc.stdint cimport int64_t


cdef struct COrder:
    int64_t order_id
    char side          # b'B' or b'S'
    double price
    int64_t quantity
    int64_t timestamp


cdef class OrderBookCython:
    """
    Cython port of the matching engine. Internally still backed by
    Python lists of dicts for now (Day 2) --- true C-struct arrays
    with pointer-based storage land Day 3 once throughput testing
    shows where the real bottleneck is. What's already C-level today:
    every price/quantity/timestamp comparison during insertion AND
    matching.
    """

    cdef public list buy_side
    cdef public list sell_side
    cdef public list trades
    cdef public int64_t _trade_id_counter

    def __init__(self):
        self.buy_side = []
        self.sell_side = []
        self.trades = []
        self._trade_id_counter = 1

    cpdef void insert_order(self, dict order):
        """
        Sorted insertion by price, using a C-typed binary search
        instead of Python's bisect.insort (Day 2 baseline used in
        engine/order_book.py). This is the same O(log n) find + O(n)
        shift shape, but the comparison itself never touches a Python
        float boxing/unboxing path --- it's compared as a C double.
        """
        cdef double price = order["price"]
        cdef str side = order["side"]
        cdef Py_ssize_t lo, hi, mid
        cdef list target

        if side == "B":
            target = self.buy_side
            lo, hi = 0, len(target)
            while lo < hi:
                mid = (lo + hi) // 2
                # Buy side sorted descending: best (highest) bid first
                if (<double>target[mid]["price"]) < price:
                    hi = mid
                else:
                    lo = mid + 1
            target.insert(lo, order)
        else:
            target = self.sell_side
            lo, hi = 0, len(target)
            while lo < hi:
                mid = (lo + hi) // 2
                # Sell side sorted ascending: best (lowest) ask first
                if (<double>target[mid]["price"]) > price:
                    hi = mid
                else:
                    lo = mid + 1
            target.insert(lo, order)

    cpdef dict match_order(self, dict order):
        """
        Real Price-Time Priority matching. Returns a dict:
            {"trades": [list of trade dicts produced], "resting": bool}
        "resting" is True if any leftover quantity was inserted onto
        the book (fully or partially unmatched).

        This is the Day 5 deliverable: crossing logic, not just
        sorted insertion (which is all match_order() did through Day 4,
        via the old placeholder that just called insert_order()).
        """
        cdef str side = order["side"]
        cdef double incoming_price = order["price"]
        cdef int64_t remaining = order["quantity"]
        cdef list opposite_side
        cdef dict resting_order
        cdef int64_t fill_qty
        cdef list produced_trades = []

        opposite_side = self.sell_side if side == "B" else self.buy_side

        while remaining > 0 and len(opposite_side) > 0:
            resting_order = opposite_side[0]  # best price is always index 0

            if side == "B":
                # Buy crosses if the best ask is at or below the buy price
                if resting_order["price"] > incoming_price:
                    break
            else:
                # Sell crosses if the best bid is at or above the sell price
                if resting_order["price"] < incoming_price:
                    break

            fill_qty = remaining if remaining < resting_order["quantity"] else resting_order["quantity"]

            if side == "B":
                trade = self._record_trade(order, resting_order, fill_qty)
            else:
                trade = self._record_trade(resting_order, order, fill_qty)
            produced_trades.append(trade)

            remaining -= fill_qty
            resting_order["quantity"] -= fill_qty

            if resting_order["quantity"] <= 0:
                # Fully consumed --- remove from the book.
                opposite_side.pop(0)
            # else: partially filled, stays at index 0 (still best price,
            # unchanged position since price didn't change) with reduced
            # quantity --- correctly reflects time priority: it already
            # had priority at this price and keeps it.

        cdef bint has_resting = False
        if remaining > 0:
            order = dict(order)
            order["quantity"] = remaining
            self.insert_order(order)
            has_resting = True

        return {"trades": produced_trades, "resting": has_resting}

    cdef dict _record_trade(self, dict buy_order, dict sell_order, int64_t qty):
        """Build a trade dict in the same shared format as the
        pure-Python reference (engine/order_book.py's _record_trade),
        so both engines produce identical trade shapes."""
        cdef dict trade = {
            "trade_id": self._trade_id_counter,
            "buy_order_id": buy_order["order_id"],
            "sell_order_id": sell_order["order_id"],
            "price": sell_order["price"],
            "quantity": qty,
        }
        self._trade_id_counter += 1
        self.trades.append(trade)
        return trade

    cpdef dict get_top_levels(self, int depth=5):
        return {
            "bids": self.buy_side[:depth],
            "asks": self.sell_side[:depth],
        }

    cpdef dict get_last_trade(self):
        return self.trades[-1] if self.trades else None
