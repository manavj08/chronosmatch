# matching_engine.pxd
# ---------------------------------------------------------------------------
# Cython header for matching_engine.pyx.
#
# Purpose: lets OTHER Cython modules `cimport` MatchingEngine and call its
# cdef/cpdef methods directly through the C vtable, skipping the Python
# attribute-lookup/call machinery entirely. This is what makes it possible,
# e.g., for a future Cython-level order-generator or IPC reader to drive the
# engine without ever touching the GIL-bound Python API. A .pyx file with no
# .pxd can still be imported from Python, but it cannot be cimported at
# C speed from other Cython code -- this file is what closes that gap.
# ---------------------------------------------------------------------------

from libc.stdint cimport int64_t


cdef struct COrder:
    int64_t order_id
    char side              # b'B' or b'S'
    double price
    int64_t quantity
    int64_t timestamp


cdef struct PriceLevel:
    double price
    COrder* orders          # FIFO array of orders resting at this price
    int64_t count            # number of orders currently in the FIFO
    int64_t capacity         # allocated size of the orders array
    int64_t head             # index of the oldest (next to match) order
    int64_t total_quantity   # running sum of resting quantity at this level,
                               # maintained incrementally so best_bid()/
                               # best_ask() are true O(1) lookups (price AND
                               # size) instead of needing to walk the FIFO


cdef struct CTrade:
    int64_t trade_id
    int64_t buy_order_id
    int64_t sell_order_id
    double price
    int64_t quantity
    int64_t entry_timestamp   # incoming order's own timestamp
    int64_t exit_timestamp    # perf_counter_ns() captured inside the nogil
                                # matching loop, at the moment the trade
                                # was recorded
    int64_t latency_ns        # exit_timestamp - entry_timestamp


cdef class MatchingEngine:
    cdef PriceLevel* _buy_levels
    cdef PriceLevel* _sell_levels
    cdef int64_t _buy_level_count
    cdef int64_t _sell_level_count

    cdef CTrade* _trades_c
    cdef int64_t _trade_count
    cdef int64_t _trade_id_counter

    # Fixed-size circular buffer of recent per-trade latencies, plus O(1)
    # lifetime running stats (min/max/sum/count) that never require sorting.
    cdef int64_t* _latency_ring
    cdef int64_t _latency_ring_next
    cdef int64_t _latency_ring_filled
    cdef int64_t _latency_count_lifetime
    cdef int64_t _latency_sum_lifetime
    cdef int64_t _latency_min_lifetime
    cdef int64_t _latency_max_lifetime

    # ---- pure-C hot path: no Python objects, no GIL requirement ----
    cdef int64_t _find_level_index(self, PriceLevel* levels, int64_t count,
                                     double price, bint is_buy_side) noexcept nogil
    cdef bint _insert_c(self, COrder order) noexcept nogil
    cdef void _remove_level_at(self, PriceLevel* levels, int64_t* level_count_ptr,
                                 int64_t idx) noexcept nogil
    cdef bint _cancel_c(self, int64_t order_id, char side) noexcept nogil
    cdef void _record_trade_c(self, int64_t buy_order_id, int64_t sell_order_id,
                                double price, int64_t qty,
                                int64_t entry_timestamp) noexcept nogil
    cdef void _record_latency_sample(self, int64_t latency_ns) noexcept nogil
    cdef int64_t _match_c(self, COrder incoming) noexcept nogil
    cdef bint _best_bid_c(self, double* out_price, int64_t* out_qty) noexcept nogil
    cdef bint _best_ask_c(self, double* out_price, int64_t* out_qty) noexcept nogil

    # ---- Python-facing edge: dict conversion happens only here ----
    cdef COrder _order_from_dict(self, dict order)
    cdef dict _order_to_dict(self, COrder c_order)

    cpdef void insert_order(self, dict order)
    cpdef bint cancel_order(self, int64_t order_id, str side)
    cpdef dict match_order(self, dict order)
    cpdef dict get_top_levels(self, int depth=*)
    cpdef dict get_last_trade(self)
    cpdef dict get_latency_stats(self)
    cpdef object best_bid(self)
    cpdef object best_ask(self)
    cpdef object spread(self)
    cpdef int64_t run_c_only_matching_cycle(self, int64_t order_id, int side,
                                              double price, int64_t quantity,
                                              int64_t timestamp)
