"""
dashboard/live_dashboard.py
-----------------------------
MEMBER C's LATENCY MONITOR (Day 7, latency display added in the
dashboard hardening pass).

Per spec: "A live terminal graph measuring the end-to-end latency in
microseconds (us)." Day 7's scope was the live Bid/Ask top-of-book
display; the latency numbers shown then were read counts and simple
timing, not the real nanosecond entry/exit instrumentation, which
didn't land in the ENGINE until Day 12-13 (matching_engine/order_book.pyx's
get_latency_stats() -- p50/p95/p99/p999/min/mean/max, computed from
real per-trade timestamps captured inside the nogil matching loop).
Day 7's docstring said the fields were "already laid out" for this,
but that turned out not to be true on inspection -- no latency numbers
were actually rendered anywhere in _draw(). Closed directly here: the
dashboard now calls the engine's own get_latency_stats() every frame
and renders p50/p95/p99/p999 in microseconds, which is the literal
spec requirement this file exists to satisfy.

This replaces the old dashboard_starter.py skeleton (see that file's
own "WHAT TO DO NEXT" comments, written before the spec pivot ---
this is the Day 5-7 progression it described, done for real). It is
a real, separate OS process: it reads orders from the same
shared-memory ring buffer as run_demo.py's matcher, runs them through
the real compiled Cython engine (matching_engine.OrderBookCython),
and renders the live order book with curses --- not a mockup, not
hardcoded numbers.

Run standalone (reads from an already-running ring buffer + generator,
e.g. via run_dashboard_demo.py), or see run_dashboard_demo.py for a
one-command way to see it live with synthetic order flow.
"""

import curses
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "matching_engine"))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from shared.ring_buffer import RingBuffer

WHALE_THRESHOLD = 50  # quantity above which a trade gets highlighted (Day 16-17 will make this configurable/polished)


def format_latency_line(stats: dict) -> str:
    """Pure formatting function for the engine's get_latency_stats()
    dict, independently testable without curses or a real terminal.
    Converts nanoseconds (the engine's native unit) to microseconds
    (the spec's stated display unit: "measuring the end-to-end latency
    in microseconds (us)"). Handles the empty-book case (count == 0)
    the same way get_latency_stats() itself does -- zeroed fields, not
    an error -- so the dashboard doesn't need a separate branch for
    "no trades yet".

    Reading the numbers this displays -- important caveat, found
    during pseudo-terminal verification of this exact display: at the
    default demo order rate (run_dashboard_demo.py), this loop reads
    and processes only ONE order per redraw frame (~50ms, matching
    stdscr.timeout(50)), which is far slower than the generator can
    produce orders. entry_timestamp is set when an order is GENERATED
    (simulator/order_generator.py), not when this loop gets around to
    reading it -- so at the demo's default rate, most of the displayed
    latency is real queueing time in the ring buffer waiting for this
    single-order-per-frame loop, not the engine's own matching speed
    (which is sub-microsecond internally -- see
    matching_engine/tests/test_latency_instrumentation.py and the
    engine-only benchmarks elsewhere in this project for that number
    measured without this loop's frame-rate ceiling in the way). This
    display is still an honest, real end-to-end latency measurement
    for THIS specific pipeline configuration; it just isn't a measure
    of the matching engine's own speed in isolation, and the two
    should not be confused when reading the screen.
    """
    if stats["count"] == 0:
        return "Latency: (no trades yet)"
    return (f"Latency (us)  p50={stats['p50_ns']/1000:.1f}  "
            f"p95={stats['p95_ns']/1000:.1f}  "
            f"p99={stats['p99_ns']/1000:.1f}  "
            f"p999={stats['p999_ns']/1000:.1f}  "
            f"(n={stats['count']:,})")


def format_whale_line(trade: dict) -> str:
    """Pure formatting function, independently testable without curses
    or a real terminal. Used by run_dashboard() below and covered
    directly by dashboard/tests/test_dashboard_logic.py."""
    return (f"WHALE: {trade['quantity']} @ {trade['price']:.2f}  "
            f"(buy #{trade['buy_order_id']} x sell #{trade['sell_order_id']})")


def update_whale_lines(whale_lines: list, trades: list, threshold: int = WHALE_THRESHOLD,
                        max_lines: int = 3) -> list:
    """Pure function: given the current whale-line history and a list
    of newly produced trades, returns the updated history (newest
    first, capped at max_lines). Extracted out of run_dashboard() so
    this logic is testable without curses or a real terminal."""
    for trade in trades:
        if trade["quantity"] >= threshold:
            whale_lines = [format_whale_line(trade)] + whale_lines
    return whale_lines[:max_lines]


def run_dashboard(stdscr, ring_buffer_capacity: int = 256, duration_seconds: float = None,
                   on_frame=None):
    """
    Real matcher + live display, combined into one process (Day 7
    keeps this simple: one process reads and renders; if a future day
    needs the matching and the display decoupled into separate
    processes communicating over their own IPC, that's a deliberate
    later change, not an oversight).

    on_frame: optional callback, called once per redraw frame as
    on_frame(book, orders_processed, trades_matched) -- lets other
    scripts (see run_full_integration_demo.py) attach a side effect
    like periodically flushing new trades to the SQLite ledger,
    without duplicating this loop or reaching into its internals.
    Exceptions from on_frame are caught and ignored per-frame (same
    reasoning as TradeFlusher's own error handling: a side effect
    failing must never crash the live display), not raised.
    """
    from order_book import OrderBookCython  # the compiled .so

    curses.curs_set(0)      # hide the blinking cursor
    stdscr.nodelay(True)    # don't block waiting for keypresses
    stdscr.timeout(50)      # refresh ~20x/second

    rb = RingBuffer(capacity=ring_buffer_capacity, create=False)
    book = OrderBookCython()

    orders_processed = 0
    trades_matched = 0
    recent_whale_lines = []  # last few whale-highlighted trades, newest first
    start_time = time.time()

    while True:
        if duration_seconds is not None and (time.time() - start_time) > duration_seconds:
            break

        order = rb.read_order()
        if order is not None:
            orders_processed += 1
            result = book.match_order(order)
            trades_matched += len(result["trades"])
            recent_whale_lines = update_whale_lines(recent_whale_lines, result["trades"])

        if on_frame is not None:
            try:
                on_frame(book, orders_processed, trades_matched)
            except Exception:
                pass  # a side-effect failure must never crash the live display

        latency_stats = book.get_latency_stats()
        _draw(stdscr, book, orders_processed, trades_matched, recent_whale_lines, latency_stats)

        key = stdscr.getch()
        if key == 3:  # Ctrl+C
            break


def _draw(stdscr, book, orders_processed: int, trades_matched: int, whale_lines: list,
          latency_stats: dict):
    stdscr.erase()
    max_y, max_x = stdscr.getmaxyx()

    def safe_addstr(y, x, text, attr=curses.A_NORMAL):
        """curses raises if you write past the terminal edge; clip
        defensively so a narrow terminal doesn't crash the dashboard."""
        if 0 <= y < max_y and 0 <= x < max_x:
            try:
                stdscr.addstr(y, x, text[:max(0, max_x - x - 1)], attr)
            except curses.error:
                pass  # bottom-right corner write, curses quirk --- harmless

    levels = book.get_top_levels(depth=5)
    last_trade = book.get_last_trade()

    safe_addstr(0, 0, "ChronosMatch — Live Order Book", curses.A_BOLD)
    safe_addstr(1, 0, "(Ctrl+C to exit)", curses.A_DIM)

    safe_addstr(3, 0, "BIDS", curses.A_BOLD)
    safe_addstr(3, 22, "ASKS", curses.A_BOLD)

    bids, asks = levels["bids"], levels["asks"]
    for i in range(max(len(bids), len(asks))):
        if i < len(bids):
            b = bids[i]
            safe_addstr(4 + i, 0, f"{b['price']:>8.2f}  x{b['quantity']}")
        if i < len(asks):
            a = asks[i]
            safe_addstr(4 + i, 22, f"{a['price']:>8.2f}  x{a['quantity']}")

    row = 4 + max(len(bids), len(asks), 1) + 1

    if last_trade:
        safe_addstr(row, 0, f"Last trade: {last_trade['price']:.2f} x{last_trade['quantity']}")
    else:
        safe_addstr(row, 0, "Last trade: (none yet)")
    row += 2

    safe_addstr(row, 0, f"Orders processed: {orders_processed}")
    safe_addstr(row + 1, 0, f"Trades matched:   {trades_matched}")
    row += 2

    safe_addstr(row, 0, format_latency_line(latency_stats), curses.A_BOLD)
    row += 2

    if whale_lines:
        safe_addstr(row, 0, "Recent whale trades:", curses.A_BOLD)
        row += 1
        for line in whale_lines:
            safe_addstr(row, 0, line, curses.A_REVERSE)
            row += 1

    stdscr.refresh()


if __name__ == "__main__":
    try:
        curses.wrapper(run_dashboard)
    except KeyboardInterrupt:
        pass
    print("Dashboard closed cleanly.")
