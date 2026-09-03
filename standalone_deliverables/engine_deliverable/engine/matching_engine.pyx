# cython: language_level=3
"""
engine/matching_engine.pyx
---------------------------
Cython limit order book / matching engine, Price-Time Priority.

Design summary
==============
Each side of the book (bids, asks) is an array of PRICE LEVELS, sorted by
price (best price at index 0). Each price level owns its own small FIFO
array of individual orders resting at that exact price. This is "price-level
bucketing": binary search happens over the (small) number of distinct price
levels, not over every individual resting order, and appending a new order
to an existing level is O(1) amortized (tail append into the level's FIFO,
no shift). Only creating a brand-new price level, or removing one that has
been fully drained, costs a shift -- and that shift is bounded by the number
of distinct price levels, not the number of individual orders. See
benchmarks/python_baseline_engine.py + benchmarks/benchmark_vs_python.py for
a measured comparison against a naive linear-scan design.

Every field that participates in matching is a C primitive:
    order_id, quantity, timestamp  -> int64_t
    price                          -> double
    side                           -> char ('B' or 'S')

The matching loop itself (_match_c) and everything it calls (_insert_c,
_cancel_c, _find_level_index, _remove_level_at, _record_trade_c,
_record_latency_sample) is declared `noexcept nogil`: no Python object is
created, read, or refcounted anywhere in that call graph, and the GIL is not
required to run it. Dict <-> struct conversion happens ONLY at the two
Python-facing edges (_order_from_dict / _order_to_dict), never inside the
hot path itself. See tests/test_matching_engine.py's GC-safety tests and
gc_demo.py for a direct, measured proof of this (not just an assertion).

    Python objects (dict order)
            |
            v   _order_from_dict()  <-- Cython boundary, GIL required
    COrder struct
            |
            v   _match_c() / _insert_c()   <-- nogil, pure C, no GC involved
    CTrade struct(s)
            |
            v   _order_to_dict() per trade  <-- Cython boundary, GIL required
    Python objects (dict trade result)
"""

from libc.stdint cimport int64_t
from libc.string cimport memmove
from libc.stdlib cimport malloc, realloc, free, qsort
from cpython.mem cimport PyMem_Malloc, PyMem_Free
from cpython.time cimport perf_counter_ns

DEF MAX_PRICE_LEVELS = 100000     # distinct price points supported per side
DEF INITIAL_LEVEL_CAPACITY = 16   # starting FIFO capacity per price level;
                                    # grows via realloc() if a level gets
                                    # deeper than this (still pure C, no
                                    # Python object involved)
DEF MAX_TRADES = 1000000
DEF LATENCY_RING_SIZE = 10000     # fixed-size circular buffer of recent
                                    # per-trade latencies, used for on-demand
                                    # percentile queries. Kept smaller than
                                    # MAX_TRADES on purpose: a percentile
                                    # query sorts a copy of this buffer, and
                                    # sorting a bounded 10,000-element buffer
                                    # is cheap and O(1)-ish relative to total
                                    # trade count, unlike sorting the full
                                    # trade history on every query.


cdef int _compare_int64(const void* a, const void* b) noexcept nogil:
    """Comparator for libc.stdlib.qsort, used by get_latency_stats() to sort
    the latency ring buffer for percentile computation. Must be a plain C
    function (not a bound method) -- qsort takes a raw function pointer."""
    cdef int64_t val_a = (<int64_t*>a)[0]
    cdef int64_t val_b = (<int64_t*>b)[0]
    if val_a < val_b:
        return -1
    elif val_a > val_b:
        return 1
    else:
        return 0


cdef class MatchingEngine:
    """
    Cython Limit Order Book with Price-Time Priority matching.

    Public (Python-facing) API:
        insert_order(order: dict) -> None
        cancel_order(order_id: int, side: str) -> bool
        match_order(order: dict) -> dict            # {"trades": [...], "resting": bool}
        best_bid() -> dict | None                    # {"price": ..., "quantity": ...}
        best_ask() -> dict | None
        spread() -> float | None
        get_top_levels(depth: int = 5) -> dict       # {"bids": [...], "asks": [...]}
        get_last_trade() -> dict | None
        get_latency_stats() -> dict
        buy_side / sell_side / trades                 (properties)

    Pure-C entry point for benchmarking / GC-safety demonstration:
        run_c_only_matching_cycle(order_id, side, price, quantity, timestamp) -> int64_t

    (All C-level attributes -- the level arrays, trade buffer, and latency
    ring -- are declared in matching_engine.pxd, not here, since a cdef
    class with an accompanying .pxd must declare its C attributes there.)
    """

    def __cinit__(self):
        self._buy_levels = <PriceLevel*>PyMem_Malloc(MAX_PRICE_LEVELS * sizeof(PriceLevel))
        self._sell_levels = <PriceLevel*>PyMem_Malloc(MAX_PRICE_LEVELS * sizeof(PriceLevel))
        self._trades_c = <CTrade*>PyMem_Malloc(MAX_TRADES * sizeof(CTrade))
        if self._buy_levels == NULL or self._sell_levels == NULL or self._trades_c == NULL:
            raise MemoryError("failed to allocate fixed-size book/trade storage")

        self._buy_level_count = 0
        self._sell_level_count = 0
        self._trade_count = 0
        self._trade_id_counter = 1

        self._latency_ring = <int64_t*>PyMem_Malloc(LATENCY_RING_SIZE * sizeof(int64_t))
        if self._latency_ring == NULL:
            raise MemoryError("failed to allocate latency ring buffer")
        self._latency_ring_next = 0
        self._latency_ring_filled = 0
        self._latency_count_lifetime = 0
        self._latency_sum_lifetime = 0
        self._latency_min_lifetime = 0
        self._latency_max_lifetime = 0

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
        if self._latency_ring is not NULL:
            PyMem_Free(self._latency_ring)

    # ------------------------------------------------------------------
    # HOT PATH -- pure C, no Python objects, nogil.
    # ------------------------------------------------------------------

    cdef int64_t _find_level_index(self, PriceLevel* levels, int64_t count,
                                     double price, bint is_buy_side) noexcept nogil:
        """Binary search for the level at exactly `price`. Returns the index
        if found, or a negative encoded value -(insertion_index) - 1 if not
        found (standard bisect-style encoding), so callers can distinguish
        "found at index N" from "not found, insert at index N" in one pass.
        """
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
        return -(lo) - 1

    cdef bint _insert_c(self, COrder order) noexcept nogil:
        """Insert an order into its price level's FIFO, creating a new level
        if none exists yet at that exact price. Appending to an existing
        level is O(1) amortized (tail append). Creating a new level costs
        O(number of distinct price levels) for the array shift -- not
        O(number of individual orders).

        Rejects orders with quantity <= 0 (would otherwise sit on the book
        as a phantom level and later produce a zero-quantity "trade" with no
        economic meaning).
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
            idx = found_or_neg
            lvl = &levels[idx]

            # Compact the FIFO if the head has drifted far enough that
            # keeping the backing array from growing forever is worthwhile.
            if lvl.head > 0 and (lvl.head + lvl.count) >= lvl.capacity:
                memmove(&lvl.orders[0], &lvl.orders[lvl.head], lvl.count * sizeof(COrder))
                lvl.head = 0

            if (lvl.head + lvl.count) >= lvl.capacity:
                new_capacity = lvl.capacity * 2
                new_orders_array = <COrder*>realloc(lvl.orders, new_capacity * sizeof(COrder))
                if new_orders_array == NULL:
                    return False
                lvl.orders = new_orders_array
                lvl.capacity = new_capacity

            lvl.orders[lvl.head + lvl.count] = order
            lvl.count += 1
            lvl.total_quantity += order.quantity
            return True

        else:
            if level_count_ptr[0] >= MAX_PRICE_LEVELS:
                return False  # capacity guard

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
            levels[idx].total_quantity = order.quantity
            level_count_ptr[0] += 1
            return True

    cdef void _remove_level_at(self, PriceLevel* levels, int64_t* level_count_ptr,
                                 int64_t idx) noexcept nogil:
        """Remove an emptied-out price level: free its FIFO backing array,
        then shift the remaining levels down. O(number of price levels)."""
        free(levels[idx].orders)
        if idx < level_count_ptr[0] - 1:
            memmove(&levels[idx], &levels[idx + 1],
                    (level_count_ptr[0] - idx - 1) * sizeof(PriceLevel))
        level_count_ptr[0] -= 1

    cdef bint _cancel_c(self, int64_t order_id, char side) noexcept nogil:
        """Cancel a resting order by id. Scans price levels on the given
        side (best price first) and, within each level, the level's own
        FIFO, looking for a matching order_id.

        Honest complexity: O(number of resting price levels + orders at the
        matching level) -- a linear scan, not O(1). A production system
        would maintain an order_id -> (level, slot) index (e.g. a hash map)
        for true O(1) cancellation; that index is deliberately not built
        here so cancellation stays entirely at the C-struct level (no
        Python dict/object involved anywhere, and this function stays
        nogil-capable like the rest of the hot path). Cancellation is not
        on the insert/match hot path this project's benchmarks measure, so
        this trade-off is reasonable for the current scope -- documented
        here rather than silently assumed to be free.
        """
        cdef PriceLevel* levels
        cdef int64_t* level_count_ptr
        cdef bint is_buy_side = (side == b'B')
        cdef int64_t i, j, k
        cdef PriceLevel* lvl
        cdef int64_t cancelled_qty

        if is_buy_side:
            levels = self._buy_levels
            level_count_ptr = &self._buy_level_count
        else:
            levels = self._sell_levels
            level_count_ptr = &self._sell_level_count

        for i in range(level_count_ptr[0]):
            lvl = &levels[i]
            for j in range(lvl.head, lvl.head + lvl.count):
                if lvl.orders[j].order_id == order_id:
                    cancelled_qty = lvl.orders[j].quantity
                    # Shift everything after j (within the active window)
                    # down by one slot to close the gap.
                    for k in range(j, lvl.head + lvl.count - 1):
                        lvl.orders[k] = lvl.orders[k + 1]
                    lvl.count -= 1
                    lvl.total_quantity -= cancelled_qty
                    if lvl.count == 0:
                        self._remove_level_at(levels, level_count_ptr, i)
                    return True
        return False

    cdef void _record_trade_c(self, int64_t buy_order_id, int64_t sell_order_id,
                                double price, int64_t qty,
                                int64_t entry_timestamp) noexcept nogil:
        """Records a trade with nanosecond entry/exit timestamps.
        entry_timestamp is the INCOMING order's own timestamp (the order
        that triggered this match by crossing the book), not the resting
        order's timestamp -- what matters for latency measurement is how
        long the system took to process the order that just arrived.
        exit_timestamp is captured HERE, inside the nogil matching loop,
        using cpython.time.perf_counter_ns() -- a nogil-safe C-level
        nanosecond clock reading the same OS clock as Python's
        time.perf_counter_ns(), without needing the GIL back.
        """
        cdef CTrade* t
        cdef int64_t now
        if self._trade_count >= MAX_TRADES:
            return
        now = perf_counter_ns()
        t = &self._trades_c[self._trade_count]
        t.trade_id = self._trade_id_counter
        t.buy_order_id = buy_order_id
        t.sell_order_id = sell_order_id
        t.price = price
        t.quantity = qty
        t.entry_timestamp = entry_timestamp
        t.exit_timestamp = now
        t.latency_ns = now - entry_timestamp
        self._trade_id_counter += 1
        self._trade_count += 1
        self._record_latency_sample(t.latency_ns)

    cdef void _record_latency_sample(self, int64_t latency_ns) noexcept nogil:
        """O(1) update of the circular latency ring and lifetime running
        stats (min/max/sum/count). No sorting, no allocation -- runs on
        every trade. Percentile computation (which needs sorting) only
        happens on demand in get_latency_stats(), over the bounded ring."""
        self._latency_ring[self._latency_ring_next] = latency_ns
        self._latency_ring_next = (self._latency_ring_next + 1) % LATENCY_RING_SIZE
        if self._latency_ring_filled < LATENCY_RING_SIZE:
            self._latency_ring_filled += 1

        self._latency_count_lifetime += 1
        self._latency_sum_lifetime += latency_ns
        if self._latency_count_lifetime == 1 or latency_ns < self._latency_min_lifetime:
            self._latency_min_lifetime = latency_ns
        if self._latency_count_lifetime == 1 or latency_ns > self._latency_max_lifetime:
            self._latency_max_lifetime = latency_ns

    cdef int64_t _match_c(self, COrder incoming) noexcept nogil:
        """Matching loop: walks price levels best-first (always index 0)
        and, within each level, walks the FIFO from `head` forward (oldest
        order first -- correct time priority). A level that empties out is
        removed via _remove_level_at(); a partially-filled order at the
        front of a level just has its quantity reduced and stays exactly
        where it is (head doesn't advance until an order is fully
        consumed) -- this is what makes the matching Price-TIME priority,
        not just Price priority.
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
                self._record_trade_c(incoming.order_id, front_order.order_id, lvl.price,
                                      fill_qty, incoming.timestamp)
            else:
                self._record_trade_c(front_order.order_id, incoming.order_id, lvl.price,
                                      fill_qty, incoming.timestamp)

            remaining -= fill_qty
            front_order.quantity -= fill_qty
            lvl.total_quantity -= fill_qty

            if front_order.quantity <= 0:
                lvl.head += 1
                lvl.count -= 1
                if lvl.count == 0:
                    self._remove_level_at(opposite_levels, opposite_level_count, 0)
            # else: partially filled, stays at the front of the FIFO with
            # reduced quantity -- correct time priority, no shift needed.

        return remaining

    cdef bint _best_bid_c(self, double* out_price, int64_t* out_qty) noexcept nogil:
        """True O(1) best-bid lookup: price is always at levels[0], and
        total resting quantity at that level is maintained incrementally
        (see PriceLevel.total_quantity) rather than summed on each call."""
        if self._buy_level_count == 0:
            return False
        out_price[0] = self._buy_levels[0].price
        out_qty[0] = self._buy_levels[0].total_quantity
        return True

    cdef bint _best_ask_c(self, double* out_price, int64_t* out_qty) noexcept nogil:
        """See _best_bid_c -- same O(1) guarantee, opposite side."""
        if self._sell_level_count == 0:
            return False
        out_price[0] = self._sell_levels[0].price
        out_qty[0] = self._sell_levels[0].total_quantity
        return True

    # ------------------------------------------------------------------
    # PYTHON-FACING API -- dict conversion happens only at this edge.
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
        """Insert a resting order onto the book (no matching attempted).
        Buy/Sell handling: `order["side"]` is 'B' or 'S'."""
        cdef COrder c_order = self._order_from_dict(order)
        self._insert_c(c_order)

    cpdef bint cancel_order(self, int64_t order_id, str side):
        """Cancel a resting order by id. `side` is 'B' or 'S' (needed since
        order ids are not required to be globally unique across sides, and
        avoiding a global id->side index keeps the engine's Python-object
        footprint minimal, per the "minimize Python objects" requirement).
        Returns True if an order was found and removed, False otherwise."""
        cdef char c_side = ord(side)
        return self._cancel_c(order_id, c_side)

    cpdef dict match_order(self, dict order):
        """Attempt to match an incoming order against the opposite side of
        the book (Price-Time Priority). Any unfilled remainder rests on the
        book. Returns {"trades": [list of trade dicts], "resting": bool}."""
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
                "entry_timestamp": self._trades_c[i].entry_timestamp,
                "exit_timestamp": self._trades_c[i].exit_timestamp,
                "latency_ns": self._trades_c[i].latency_ns,
            })

        if remaining > 0:
            c_order.quantity = remaining
            self._insert_c(c_order)
            has_resting = True

        return {"trades": produced_trades, "resting": has_resting}

    @property
    def buy_side(self):
        """Flat list of resting buy orders, best price first, correct time
        priority within each price level. Built fresh from the level+FIFO
        C storage on access -- convenient for tests/inspection; the hot
        path never uses this."""
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
        """See buy_side -- same tradeoff, opposite side."""
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
                "entry_timestamp": self._trades_c[i].entry_timestamp,
                "exit_timestamp": self._trades_c[i].exit_timestamp,
                "latency_ns": self._trades_c[i].latency_ns,
            }
            for i in range(self._trade_count)
        ]

    cpdef dict get_top_levels(self, int depth=5):
        """Top N PRICE LEVELS per side (not N individual orders). Each
        level's own front order (the next to match) represents that level.
        Best price first on each side."""
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

    cpdef object best_bid(self):
        """Best (highest) resting buy price and total resting quantity at
        that price, or None if the buy side is empty. O(1)."""
        cdef double price
        cdef int64_t qty
        if self._best_bid_c(&price, &qty):
            return {"price": price, "quantity": qty}
        return None

    cpdef object best_ask(self):
        """Best (lowest) resting sell price and total resting quantity at
        that price, or None if the sell side is empty. O(1)."""
        cdef double price
        cdef int64_t qty
        if self._best_ask_c(&price, &qty):
            return {"price": price, "quantity": qty}
        return None

    cpdef object spread(self):
        """best_ask.price - best_bid.price, or None if either side is
        empty (spread is undefined without both a bid and an ask). O(1)."""
        cdef double bid_price, ask_price
        cdef int64_t bid_qty, ask_qty
        cdef bint has_bid = self._best_bid_c(&bid_price, &bid_qty)
        cdef bint has_ask = self._best_ask_c(&ask_price, &ask_qty)
        if not has_bid or not has_ask:
            return None
        return ask_price - bid_price

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
            "entry_timestamp": t.entry_timestamp,
            "exit_timestamp": t.exit_timestamp,
            "latency_ns": t.latency_ns,
        }

    cpdef dict get_latency_stats(self):
        """
        Live latency percentiles/stats for the matching engine.

        min/mean/max/count are lifetime, O(1) running stats (always exact).
        p50/p95/p99/p999 are computed on demand from the bounded circular
        ring of the most recent LATENCY_RING_SIZE trades (sorted via
        libc.stdlib.qsort over a COPY of the ring -- the live ring itself is
        never mutated by a stats query, so calling this has no effect on
        the matching loop's own state).
        """
        cdef int64_t n = self._latency_ring_filled
        if n == 0 or self._latency_count_lifetime == 0:
            return {
                "count": 0, "min_ns": 0, "mean_ns": 0, "max_ns": 0,
                "p50_ns": 0, "p95_ns": 0, "p99_ns": 0, "p999_ns": 0,
            }

        cdef int64_t* sorted_copy = <int64_t*>malloc(n * sizeof(int64_t))
        cdef int64_t i
        if sorted_copy == NULL:
            return {
                "count": self._latency_count_lifetime,
                "min_ns": self._latency_min_lifetime,
                "mean_ns": self._latency_sum_lifetime // self._latency_count_lifetime,
                "max_ns": self._latency_max_lifetime,
                "p50_ns": 0, "p95_ns": 0, "p99_ns": 0, "p999_ns": 0,
            }

        for i in range(n):
            sorted_copy[i] = self._latency_ring[i]
        qsort(sorted_copy, n, sizeof(int64_t), _compare_int64)

        cdef int64_t p50_idx = n // 2
        cdef int64_t p95_idx = <int64_t>(n * 0.95)
        cdef int64_t p99_idx = <int64_t>(n * 0.99)
        cdef int64_t p999_idx = <int64_t>(n * 0.999)
        if p95_idx >= n:
            p95_idx = n - 1
        if p99_idx >= n:
            p99_idx = n - 1
        if p999_idx >= n:
            p999_idx = n - 1

        cdef dict result = {
            "count": self._latency_count_lifetime,
            "min_ns": self._latency_min_lifetime,
            "mean_ns": self._latency_sum_lifetime // self._latency_count_lifetime,
            "max_ns": self._latency_max_lifetime,
            "p50_ns": sorted_copy[p50_idx],
            "p95_ns": sorted_copy[p95_idx],
            "p99_ns": sorted_copy[p99_idx],
            "p999_ns": sorted_copy[p999_idx],
        }
        free(sorted_copy)
        return result

    cpdef int64_t run_c_only_matching_cycle(self, int64_t order_id, int side,
                                              double price, int64_t quantity,
                                              int64_t timestamp):
        """Full insert-or-match cycle for one order, using ONLY the C
        struct path -- no dict is created or read anywhere in this call.
        Used by benchmarks and the GC-safety tests to measure/prove the
        engine's true hot-path cost, isolated from Python dict-conversion
        overhead at the edges. Returns remaining unmatched quantity (0 if
        fully filled)."""
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
