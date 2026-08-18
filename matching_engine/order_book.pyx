# cython: language_level=3
"""
matching_engine/order_book.pyx
--------------------------------
CYTHON LIMIT ORDER BOOK.

Day 2: first working .pyx compiled to a real C-extension.
Day 5: real Price-Time Priority matching (crossing) added.
Day 6: rewrote internal storage to C struct arrays --- no Python
objects, no GC tracking, in the matching loop.

Day 10: C-LEVEL OPTIMIZATION PASS. Profiling (see
benchmarks/level_bucketing_benchmark.py) found a real bottleneck in
the Day 6 design: each side of the book was ONE flat sorted array of
individual orders. Inserting a new order meant a binary search over
every order (fine, O(log n)) followed by an array shift (memmove) to
make room --- O(n) in the worst case, since every order behind the
insertion point has to move. Measured on this benchmark machine:
worst-case adversarial insertion (unique price every time, always the
best price) degraded from ~235,000 inserts/sec at shallow depth to
~14,500 inserts/sec at 99,000 resting orders --- a ~16x slowdown.

Fix: PRICE-LEVEL BUCKETING, matching how real exchanges structure an
order book. Each side is now an array of price LEVELS (typically far
fewer than the number of individual orders --- real markets have a
bounded number of active price points, even under heavy volume), and
each level holds its own small FIFO array of orders at that exact
price. Binary search now operates over LEVELS, not over every order,
and appending a new order to an existing level's FIFO is O(1)
amortized (no shift needed --- it goes at the tail). A brand new price
level still requires a shift of the (much smaller) level array, and a
level that empties out still requires removing it from that array ---
both real costs, but bounded by the number of distinct prices instead
of the number of individual orders.

order_id, quantity, timestamp -> C long long (int64_t)
price -> C double
side -> C char ('B' or 'S')
"""

from libc.stdint cimport int64_t
from libc.string cimport memmove
from libc.stdlib cimport malloc, realloc, free
from cpython.mem cimport PyMem_Malloc, PyMem_Free

DEF MAX_PRICE_LEVELS = 100000    # distinct price points per side. Set
                                  # to match Day 6's MAX_BOOK_DEPTH
                                  # (100,000) so the rewrite doesn't
                                  # silently reduce the book's maximum
                                  # capacity --- an early version of
                                  # this file used a smaller value
                                  # (10,000) on the assumption that
                                  # real books have far fewer distinct
                                  # prices than individual orders, but
                                  # re-running the worst-case benchmark
                                  # after the rewrite (adversarial
                                  # unique-price-every-order pattern)
                                  # showed it silently dropped 89,000
                                  # of 99,000 orders once the level
                                  # array filled --- a real capacity
                                  # regression versus Day 6, caught by
                                  # testing rather than assumed safe.
DEF INITIAL_LEVEL_CAPACITY = 16  # starting FIFO capacity per price
                                  # level; grows via realloc() if a
                                  # single price level gets deeper than
                                  # this (still pure C, no Python object)
DEF MAX_TRADES = 1000000


cdef struct COrder:
    int64_t order_id
    char side          # b'B' or b'S'
    double price
    int64_t quantity
    int64_t timestamp


cdef struct PriceLevel:
    double price
    COrder* orders           # FIFO array of orders at this price
    int64_t count             # number of orders currently in this level
    int64_t capacity          # allocated size of the orders array
    int64_t head              # index of the oldest (next to match) order;
                                # advances on removal instead of shifting
                                # the whole array on every fill, amortizing
                                # the cost of removing from the front


cdef struct CTrade:
    int64_t trade_id
    int64_t buy_order_id
    int64_t sell_order_id
    double price
    int64_t quantity


cdef class OrderBookCython:
    """
    Cython Limit Order Book. Day 10 storage: each side is an array of
    PriceLevel structs (sorted by price), each holding its own FIFO
    array of COrder structs. No Python objects anywhere in the hot
    path --- same GC-safety guarantee as Day 6, now with better
    insertion complexity under deep, many-price-level conditions.
    """

    cdef PriceLevel* _buy_levels
    cdef PriceLevel* _sell_levels
    cdef int64_t _buy_level_count
    cdef int64_t _sell_level_count

    cdef CTrade* _trades_c
    cdef int64_t _trade_count
    cdef int64_t _trade_id_counter

    def __cinit__(self):
        self._buy_levels = <PriceLevel*>PyMem_Malloc(MAX_PRICE_LEVELS * sizeof(PriceLevel))
        self._sell_levels = <PriceLevel*>PyMem_Malloc(MAX_PRICE_LEVELS * sizeof(PriceLevel))
        self._trades_c = <CTrade*>PyMem_Malloc(MAX_TRADES * sizeof(CTrade))
        self._buy_level_count = 0
        self._sell_level_count = 0
        self._trade_count = 0
        self._trade_id_counter = 1

    def __dealloc__(self):
        cdef int64_t i
        if self._buy_levels is not NULL:
            for i in range(self._buy_level_count):
                if self._buy_levels[i].orders is not NULL:
                    free(self._buy_levels[i].orders)
            PyMem_Free(self._buy_levels)
        if self._sell_levels is not NULL:
            for i in range(self._sell_level_count):
                if self._sell_levels[i].orders is not NULL:
                    free(self._sell_levels[i].orders)
            PyMem_Free(self._sell_levels)
        if self._trades_c is not NULL:
            PyMem_Free(self._trades_c)

    # ------------------------------------------------------------------
    # HOT PATH --- pure C, no Python objects. Day 10: operates on price
    # levels + per-level FIFOs instead of one flat per-order array.
    # ------------------------------------------------------------------

    cdef int64_t _find_level_index(self, PriceLevel* levels, int64_t count,
                                     double price, bint is_buy_side) noexcept nogil:
        """Binary search for the level at exactly `price`, or the
        correct insertion index if no such level exists yet. Returns
        a NEGATIVE encoded value if the exact price wasn't found:
        -(insertion_index) - 1 (a standard bisect-style encoding),
        so callers can distinguish 'found at index N' from 'not
        found, would insert at index N' without a second search."""
        cdef Py_ssize_t lo, hi, mid
        lo, hi = 0, count
        while lo < hi:
            mid = (lo + hi) // 2
            if is_buy_side:
                # Buy levels sorted descending: best (highest) bid first
                if levels[mid].price == price:
                    return mid
                elif levels[mid].price < price:
                    hi = mid
                else:
                    lo = mid + 1
            else:
                # Sell levels sorted ascending: best (lowest) ask first
                if levels[mid].price == price:
                    return mid
                elif levels[mid].price > price:
                    hi = mid
                else:
                    lo = mid + 1
        return -(lo) - 1  # not found; caller decodes insertion index as -(result) - 1

    cdef bint _insert_c(self, COrder order) noexcept nogil:
        """Insert an order into its price level's FIFO, creating a new
        level if none exists yet at that exact price. Appending to an
        existing level's FIFO is O(1) amortized (tail append, no
        shift). Creating a brand-new level still shifts the level
        array --- O(number of distinct price levels), not O(number of
        individual orders), which is the whole point of Day 10's fix.

        Day 11 fix: rejects orders with quantity <= 0. Found via
        edge-case testing: a zero-quantity order could previously be
        inserted onto the book and would later produce a phantom
        trade with quantity: 0 when something matched against it ---
        a fake execution with no real economic meaning. Returns False
        (order rejected, nothing inserted) for such orders, same
        signature/convention as the MAX_BOOK_DEPTH capacity guard.
        """
        cdef PriceLevel* levels
        cdef int64_t* level_count_ptr
        cdef bint is_buy_side = (order.side == b'B')
        cdef int64_t found_or_neg
        cdef int64_t idx
        cdef PriceLevel* lvl
        cdef COrder* new_orders_array
        cdef int64_t new_capacity

        if order.quantity <= 0:
            return False

        if is_buy_side:
            levels = self._buy_levels
            level_count_ptr = &self._buy_level_count
        else:
            levels = self._sell_levels
            level_count_ptr = &self._sell_level_count

        found_or_neg = self._find_level_index(levels, level_count_ptr[0], order.price, is_buy_side)

        if found_or_neg >= 0:
            # Existing price level --- append to its FIFO tail.
            idx = found_or_neg
            lvl = &levels[idx]

            # Compact the FIFO if head has drifted far enough that the
            # logical array (from head to head+count) would otherwise
            # need more backing capacity than a compaction would free
            # up --- keeps a level that fills and drains repeatedly at
            # the same price from growing its backing array forever.
            if lvl.head > 0 and (lvl.head + lvl.count) >= lvl.capacity:
                memmove(&lvl.orders[0], &lvl.orders[lvl.head], lvl.count * sizeof(COrder))
                lvl.head = 0

            if (lvl.head + lvl.count) >= lvl.capacity:
                new_capacity = lvl.capacity * 2
                new_orders_array = <COrder*>realloc(lvl.orders, new_capacity * sizeof(COrder))
                if new_orders_array == NULL:
                    return False  # allocation failed; drop the order rather than corrupt state
                lvl.orders = new_orders_array
                lvl.capacity = new_capacity

            lvl.orders[lvl.head + lvl.count] = order
            lvl.count += 1
            return True

        else:
            # No level at this price yet --- create one. This is the
            # part that still costs O(number of price levels): shift
            # the level array to make room for the new level, same
            # binary-search-then-memmove pattern as Day 6, just over
            # LEVELS now instead of individual orders.
            if level_count_ptr[0] >= MAX_PRICE_LEVELS:
                return False  # capacity guard, same reasoning as Day 6's overflow fix

            idx = -(found_or_neg) - 1

            if idx < level_count_ptr[0]:
                memmove(&levels[idx + 1], &levels[idx],
                        (level_count_ptr[0] - idx) * sizeof(PriceLevel))

            levels[idx].price = order.price
            levels[idx].orders = <COrder*>malloc(INITIAL_LEVEL_CAPACITY * sizeof(COrder))
            if levels[idx].orders == NULL:
                return False
            levels[idx].orders[0] = order
            levels[idx].count = 1
            levels[idx].capacity = INITIAL_LEVEL_CAPACITY
            levels[idx].head = 0
            level_count_ptr[0] += 1
            return True

    cdef void _remove_level_at(self, PriceLevel* levels, int64_t* level_count_ptr,
                                 int64_t idx) noexcept nogil:
        """Remove an emptied-out price level from the level array.
        Frees that level's FIFO backing array, then shifts the
        remaining levels down --- O(number of price levels), same
        bound as level creation above."""
        free(levels[idx].orders)
        if idx < level_count_ptr[0] - 1:
            memmove(&levels[idx], &levels[idx + 1],
                    (level_count_ptr[0] - idx - 1) * sizeof(PriceLevel))
        level_count_ptr[0] -= 1

    cdef void _record_trade_c(self, int64_t buy_order_id, int64_t sell_order_id,
                                double price, int64_t qty) noexcept nogil:
        cdef CTrade* t
        if self._trade_count >= MAX_TRADES:
            return
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
        Matching loop, Day 10 shape: walks price LEVELS (best first,
        always index 0) and within each level, walks the FIFO from
        `head` forward --- oldest order first, correct time priority.
        A level that empties out is removed via _remove_level_at();
        a partially-filled order at the front of a level just has its
        quantity reduced and stays exactly where it is (head doesn't
        advance until an order is fully consumed).
        """
        cdef PriceLevel* opposite_levels
        cdef int64_t* opposite_level_count
        cdef int64_t remaining = incoming.quantity
        cdef int64_t fill_qty
        cdef bint crosses
        cdef bint is_buy_side = (incoming.side == b'B')
        cdef PriceLevel* lvl
        cdef COrder* front_order

        if is_buy_side:
            opposite_levels = self._sell_levels
            opposite_level_count = &self._sell_level_count
        else:
            opposite_levels = self._buy_levels
            opposite_level_count = &self._buy_level_count

        while remaining > 0 and opposite_level_count[0] > 0:
            lvl = &opposite_levels[0]  # best price level always at index 0

            if is_buy_side:
                crosses = lvl.price <= incoming.price
            else:
                crosses = lvl.price >= incoming.price

            if not crosses:
                break

            front_order = &lvl.orders[lvl.head]
            fill_qty = remaining if remaining < front_order.quantity else front_order.quantity

            if is_buy_side:
                self._record_trade_c(incoming.order_id, front_order.order_id, lvl.price, fill_qty)
            else:
                self._record_trade_c(front_order.order_id, incoming.order_id, lvl.price, fill_qty)

            remaining -= fill_qty
            front_order.quantity -= fill_qty

            if front_order.quantity <= 0:
                lvl.head += 1
                lvl.count -= 1
                if lvl.count == 0:
                    self._remove_level_at(opposite_levels, opposite_level_count, 0)
            # else: partially filled, stays at the front of the FIFO
            # (head unchanged) with reduced quantity --- correct time
            # priority, no shift needed.

        return remaining

    # ------------------------------------------------------------------
    # PYTHON-FACING API --- dict in, dict out. Same public shape as
    # Day 6; conversion happens only at this edge, never in the hot path.
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
        cdef COrder c_order = self._order_from_dict(order)
        self._insert_c(c_order)

    cpdef dict match_order(self, dict order):
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
        """Python-facing view, built fresh from the level+FIFO C
        storage on access --- same public shape as Day 6 (a flat list
        of order dicts, best price first, correct time priority
        within each price), just assembled from levels now instead of
        one flat array."""
        cdef list result = []
        cdef int64_t i, j
        cdef PriceLevel* lvl
        for i in range(self._buy_level_count):
            lvl = &self._buy_levels[i]
            for j in range(lvl.head, lvl.head + lvl.count):
                result.append(self._order_to_dict(lvl.orders[j]))
        return result

    @property
    def sell_side(self):
        """See buy_side docstring --- same tradeoff, opposite side."""
        cdef list result = []
        cdef int64_t i, j
        cdef PriceLevel* lvl
        for i in range(self._sell_level_count):
            lvl = &self._sell_levels[i]
            for j in range(lvl.head, lvl.head + lvl.count):
                result.append(self._order_to_dict(lvl.orders[j]))
        return result

    @property
    def trades(self):
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
        """Returns the top N PRICE LEVELS per side (not N individual
        orders) --- same public contract as Day 6 had, since Day 6's
        flat-array design also effectively showed one entry per order
        at the front of the array; here, each level's own FRONT order
        (the next one to match) represents that level in the top-N
        view, keeping the same dashboard-facing shape (a list of
        dicts with price/quantity/etc, best first)."""
        cdef dict result = {"bids": [], "asks": []}
        cdef int64_t n_bid_levels = min(depth, self._buy_level_count)
        cdef int64_t n_ask_levels = min(depth, self._sell_level_count)
        cdef int64_t i
        cdef PriceLevel* lvl

        for i in range(n_bid_levels):
            lvl = &self._buy_levels[i]
            result["bids"].append(self._order_to_dict(lvl.orders[lvl.head]))
        for i in range(n_ask_levels):
            lvl = &self._sell_levels[i]
            result["asks"].append(self._order_to_dict(lvl.orders[lvl.head]))
        return result

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

    cpdef int64_t run_c_only_matching_cycle(self, int64_t order_id, int side,
                                              double price, int64_t quantity,
                                              int64_t timestamp):
        """Full insert-or-match cycle for one order, using ONLY the C
        struct path --- no dict is created or read anywhere in this
        call. Mirrors match_order()'s shape (match, then insert any
        remainder). Returns remaining unmatched quantity (0 if fully
        filled)."""
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
