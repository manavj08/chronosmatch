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

Matching logic (price-time priority crossing) is still a placeholder
here --- lands Day 6 alongside GC-pause verification. Day 2's scope is
proving the toolchain works and getting sorted insertion running at
the C level.
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
    every price/quantity/timestamp comparison during insertion.
    """

    cdef public list buy_side
    cdef public list sell_side

    def __init__(self):
        self.buy_side = []
        self.sell_side = []

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

    cpdef dict get_top_levels(self, int depth=5):
        return {
            "bids": self.buy_side[:depth],
            "asks": self.sell_side[:depth],
        }
