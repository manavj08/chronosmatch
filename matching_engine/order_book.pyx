# cython: language_level=3
"""
matching_engine/order_book.pyx
--------------------------------
CYTHON LIMIT ORDER BOOK.

Day 2: first working .pyx compiled to a real C-extension. Ports the
sorted-insertion logic that used to live in engine/order_book.py
(pure Python), but with statically-typed C variables instead of
Python objects.

Day 5: real Price-Time Priority matching (crossing) added.

Day 6: THIS is the day the spec's actual requirement gets met ---
"removing all Python object interactions inside the matching loop to
guarantee the Garbage Collector never triggers during a trade."

What changed and why:

Through Day 5, orders were stored as Python dicts inside Python
lists. Every insert/match touched real Python objects: dict lookups
(order["price"]), list .insert()/.pop(0) calls, and a fresh dict
allocated for every single trade. All of that is exactly what the GC
tracks --- so even though the comparisons used C types, the STORAGE
itself was still fully within the GC's view. That does not satisfy
the spec.

Day 6 replaces internal storage with two fixed-capacity C arrays of
a plain C struct (COrder) --- no PyObject anywhere in them. Insertion,
matching, and trade recording (_match_c) now operate ENTIRELY on
these arrays: no dict access, no list method calls, no per-trade
object allocation. Trades are also recorded into a fixed-capacity C
array of a CTrade struct, not a Python dict.

The public API (insert_order(), match_order(), get_top_levels(),
get_last_trade(), the buy_side/sell_side properties) still accepts
and returns Python dicts, because the rest of the codebase (tests,
run_demo.py, the eventual dashboard) needs that. Converting a C
struct to a dict for a caller who asked for one IS a Python object
allocation --- but it only happens at the EDGE, once per call, for
whatever the caller explicitly requested to see. It never happens
inside the matching loop itself. That distinction is verified by
Day 6's GC instrumentation test (test_gc_safety.py), which calls
run_c_only_matching_cycle() directly (bypassing the dict-conversion
edge entirely), not the dict-returning wrapper.

order_id, quantity, timestamp -> C long long (int64_t)
price -> C double
side -> C char ('B' or 'S')
"""

from libc.stdint cimport int64_t
from libc.string cimport memmove
from cpython.mem cimport PyMem_Malloc, PyMem_Free

# Fixed capacity for the C-array-backed book. A real production engine
# would grow this dynamically or use a different structure entirely for
# unbounded depth; a fixed cap keeps this file's memory layout simple
# and is more than enough depth for any realistic order book while
# still being pure pre-allocated C memory (no per-order malloc).
DEF MAX_BOOK_DEPTH = 100000
DEF MAX_TRADES = 1000000


cdef struct COrder:
    int64_t order_id
    char side          # b'B' or b'S'
    double price
    int64_t quantity
    int64_t timestamp


cdef struct CTrade:
    int64_t trade_id
    int64_t buy_order_id
    int64_t sell_order_id
    double price
    int64_t quantity


cdef class OrderBookCython:
    """
    Cython Limit Order Book. Internal storage (Day 6 onward) is two
    fixed-capacity C arrays of COrder --- no Python objects, no GC
    tracking, no per-order heap allocation via malloc/free either
    (the arrays are allocated once, in __cinit__, and reused for the
    life of the object).
    """

    # Raw C storage --- NOT visible to Python directly. This is the
    # actual hot-path data; nothing here is a PyObject.
    cdef COrder* _buy_orders
    cdef COrder* _sell_orders
    cdef int64_t _buy_count
    cdef int64_t _sell_count

    cdef CTrade* _trades_c
    cdef int64_t _trade_count
    cdef int64_t _trade_id_counter

    def __cinit__(self):
        self._buy_orders = <COrder*>PyMem_Malloc(MAX_BOOK_DEPTH * sizeof(COrder))
        self._sell_orders = <COrder*>PyMem_Malloc(MAX_BOOK_DEPTH * sizeof(COrder))
        self._trades_c = <CTrade*>PyMem_Malloc(MAX_TRADES * sizeof(CTrade))
        self._buy_count = 0
        self._sell_count = 0
        self._trade_count = 0
        self._trade_id_counter = 1

    def __dealloc__(self):
        if self._buy_orders is not NULL:
            PyMem_Free(self._buy_orders)
        if self._sell_orders is not NULL:
            PyMem_Free(self._sell_orders)
        if self._trades_c is not NULL:
            PyMem_Free(self._trades_c)

    # ------------------------------------------------------------------
    # HOT PATH --- pure C, no Python objects, no dict/list access.
    # This is what Day 6's GC-safety test exercises directly.
    # ------------------------------------------------------------------

    cdef bint _insert_c(self, COrder order) noexcept nogil:
        """Sorted insertion directly into the C array via binary
        search + memmove. No Python objects touched at all --- this
        function makes no Python C-API calls, so it's safe to run
        with the GIL released (declared nogil).

        Returns False (and drops the order) if the book side is
        already at MAX_BOOK_DEPTH capacity, rather than writing past
        the end of the pre-allocated array. This bound check was
        added after a 200,000-iteration one-sided stress test (see
        test_gc_safety.py) silently overflowed the sell-side array
        past its allocated capacity, corrupting adjacent heap memory
        and causing a later, seemingly-unrelated segfault. A
        production version would need a real policy here (reject the
        order upstream, widen the depth, evict the worst price level,
        etc.) --- dropping silently is a placeholder, tracked for a
        later day, not a real capacity-management design."""
        cdef Py_ssize_t lo, hi, mid
        cdef COrder* arr
        cdef int64_t* count_ptr

        if order.side == b'B':
            arr = self._buy_orders
            count_ptr = &self._buy_count
        else:
            arr = self._sell_orders
            count_ptr = &self._sell_count

        if count_ptr[0] >= MAX_BOOK_DEPTH:
            return False

        lo, hi = 0, count_ptr[0]
        if order.side == b'B':
            while lo < hi:
                mid = (lo + hi) // 2
                if arr[mid].price < order.price:
                    hi = mid
                else:
                    lo = mid + 1
        else:
            while lo < hi:
                mid = (lo + hi) // 2
                if arr[mid].price > order.price:
                    hi = mid
                else:
                    lo = mid + 1

        # Shift everything from lo onward right by one slot, then
        # place the new order at lo. memmove handles overlapping
        # regions correctly (unlike memcpy).
        if lo < count_ptr[0]:
            memmove(&arr[lo + 1], &arr[lo], (count_ptr[0] - lo) * sizeof(COrder))
        arr[lo] = order
        count_ptr[0] += 1
        return True

    cdef void _record_trade_c(self, int64_t buy_order_id, int64_t sell_order_id,
                                double price, int64_t qty) noexcept nogil:
        """Append a trade into the pre-allocated C trade array. No
        dict allocation, no Python object of any kind."""
        cdef CTrade* t
        if self._trade_count >= MAX_TRADES:
            return  # pre-allocated capacity exhausted; drop silently
                     # (a production version would grow or flush to
                     # the database ledger here --- Day 14)
        t = &self._trades_c[self._trade_count]
        t.trade_id = self._trade_id_counter
        t.buy_order_id = buy_order_id
        t.sell_order_id = sell_order_id
        t.price = price
        t.quantity = qty
        self._trade_id_counter += 1
        self._trade_count += 1

    cdef int64_t _match_c(self, COrder incoming) noexcept nogil:
        """
        THE ACTUAL MATCHING LOOP. Pure C: struct array reads/writes,
        integer/double comparisons, memmove for removal. No dict, no
        list, no Python object allocated anywhere in this function.

        Returns the remaining unmatched quantity (0 if fully filled).
        Produced trades are recorded via _record_trade_c() directly
        into the C trade array --- the caller reads them back via
        get_top_levels()/get_last_trade() afterward if it wants a
        Python view, but nothing here allocates one.
        """
        cdef COrder* opposite
        cdef int64_t* opposite_count
        cdef int64_t remaining = incoming.quantity
        cdef int64_t fill_qty
        cdef bint crosses

        if incoming.side == b'B':
            opposite = self._sell_orders
            opposite_count = &self._sell_count
        else:
            opposite = self._buy_orders
            opposite_count = &self._buy_count

        while remaining > 0 and opposite_count[0] > 0:
            # Best price is always index 0 (arrays are kept sorted).
            if incoming.side == b'B':
                crosses = opposite[0].price <= incoming.price
            else:
                crosses = opposite[0].price >= incoming.price

            if not crosses:
                break

            fill_qty = remaining if remaining < opposite[0].quantity else opposite[0].quantity

            if incoming.side == b'B':
                self._record_trade_c(incoming.order_id, opposite[0].order_id,
                                      opposite[0].price, fill_qty)
            else:
                self._record_trade_c(opposite[0].order_id, incoming.order_id,
                                      opposite[0].price, fill_qty)

            remaining -= fill_qty
            opposite[0].quantity -= fill_qty

            if opposite[0].quantity <= 0:
                # Fully consumed: shift the whole array left by one to
                # remove index 0. memmove handles the overlap safely.
                if opposite_count[0] > 1:
                    memmove(&opposite[0], &opposite[1],
                            (opposite_count[0] - 1) * sizeof(COrder))
                opposite_count[0] -= 1
            # else: partially filled, stays at index 0 with reduced
            # quantity --- correct time priority, no array shift needed.

        return remaining

    # ------------------------------------------------------------------
    # PYTHON-FACING API --- dict in, dict out, exactly like Day 5.
    # Conversion between COrder/CTrade structs and Python dicts happens
    # ONLY here, at the edge, never inside _insert_c/_match_c above.
    # ------------------------------------------------------------------

    cdef COrder _order_from_dict(self, dict order):
        cdef COrder c_order
        cdef object side_val = order["side"]
        c_order.order_id = order["order_id"]
        c_order.side = ord(side_val) if isinstance(side_val, str) else side_val
        c_order.price = order["price"]
        c_order.quantity = order["quantity"]
        c_order.timestamp = order.get("timestamp", 0)
        return c_order

    cdef dict _order_to_dict(self, COrder c_order):
        return {
            "order_id": c_order.order_id,
            "side": chr(c_order.side),
            "price": c_order.price,
            "quantity": c_order.quantity,
            "timestamp": c_order.timestamp,
        }

    cpdef void insert_order(self, dict order):
        """Public API: accepts a dict (for compatibility with the rest
        of the codebase), converts to a C struct at this one edge, and
        calls the pure-C insertion function."""
        cdef COrder c_order = self._order_from_dict(order)
        self._insert_c(c_order)

    cpdef dict match_order(self, dict order):
        """
        Public API: real Price-Time Priority matching. Returns:
            {"trades": [list of trade dicts produced], "resting": bool}

        The actual matching work happens in _match_c() (pure C, no
        Python objects). This wrapper converts the incoming dict to a
        C struct, calls _match_c(), and converts whatever trades were
        produced back to dicts ONLY for the return value --- the
        matching decisions themselves never touched a dict.
        """
        cdef COrder c_order = self._order_from_dict(order)
        cdef int64_t trades_before = self._trade_count
        cdef int64_t remaining = self._match_c(c_order)
        cdef int64_t i
        cdef list produced_trades = []
        cdef bint has_resting = False

        for i in range(trades_before, self._trade_count):
            produced_trades.append({
                "trade_id": self._trades_c[i].trade_id,
                "buy_order_id": self._trades_c[i].buy_order_id,
                "sell_order_id": self._trades_c[i].sell_order_id,
                "price": self._trades_c[i].price,
                "quantity": self._trades_c[i].quantity,
            })

        if remaining > 0:
            c_order.quantity = remaining
            self._insert_c(c_order)
            has_resting = True

        return {"trades": produced_trades, "resting": has_resting}

    @property
    def buy_side(self):
        """Python-facing view of the buy side, built fresh from the C
        array on access. NOT the hot-path storage itself --- this
        property exists for compatibility with code/tests that expect
        a list of dicts (unchanged public shape since Day 2), and for
        the eventual dashboard. Calling this allocates Python dicts;
        the matching loop itself never does."""
        return [self._order_to_dict(self._buy_orders[i]) for i in range(self._buy_count)]

    @property
    def sell_side(self):
        """See buy_side docstring --- same tradeoff, opposite side."""
        return [self._order_to_dict(self._sell_orders[i]) for i in range(self._sell_count)]

    @property
    def trades(self):
        """Python-facing view of all recorded trades. See buy_side."""
        return [
            {
                "trade_id": self._trades_c[i].trade_id,
                "buy_order_id": self._trades_c[i].buy_order_id,
                "sell_order_id": self._trades_c[i].sell_order_id,
                "price": self._trades_c[i].price,
                "quantity": self._trades_c[i].quantity,
            }
            for i in range(self._trade_count)
        ]

    cpdef dict get_top_levels(self, int depth=5):
        cdef int64_t n_bids = min(depth, self._buy_count)
        cdef int64_t n_asks = min(depth, self._sell_count)
        return {
            "bids": [self._order_to_dict(self._buy_orders[i]) for i in range(n_bids)],
            "asks": [self._order_to_dict(self._sell_orders[i]) for i in range(n_asks)],
        }

    cpdef dict get_last_trade(self):
        if self._trade_count == 0:
            return None
        cdef CTrade t = self._trades_c[self._trade_count - 1]
        return {
            "trade_id": t.trade_id,
            "buy_order_id": t.buy_order_id,
            "sell_order_id": t.sell_order_id,
            "price": t.price,
            "quantity": t.quantity,
        }

    # ------------------------------------------------------------------
    # Day 6 GC-safety verification helper. See
    # matching_engine/tests/test_gc_safety.py --- this method runs
    # matching ENTIRELY through the C path (no dict conversion at all,
    # not even at the edge) so the GC-pause test measures the actual
    # hot loop, not the Python-facing convenience wrapper.
    # ------------------------------------------------------------------
    cpdef int64_t run_c_only_matching_cycle(self, int64_t order_id, int side,
                                              double price, int64_t quantity,
                                              int64_t timestamp):
        """Full insert-or-match cycle for one order, using ONLY the C
        struct path --- no dict is created or read anywhere in this
        call. `side` is an int here (ord('B') or ord('S')) since cpdef
        methods callable from pure Python can't take a raw C char
        parameter directly.

        Mirrors what match_order() does (match against the opposite
        side, then insert any unmatched remainder onto this order's
        own side) so this is a realistic full order-processing cycle
        for the GC-safety benchmark, not just a partial operation.
        Returns remaining unmatched quantity (0 if fully filled)."""
        cdef COrder c_order
        c_order.order_id = order_id
        c_order.side = <char>side
        c_order.price = price
        c_order.quantity = quantity
        c_order.timestamp = timestamp

        cdef int64_t remaining = self._match_c(c_order)
        if remaining > 0:
            c_order.quantity = remaining
            self._insert_c(c_order)
        return remaining
