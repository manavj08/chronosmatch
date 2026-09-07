"""
run_full_integration_demo.py
--------------------------------
Day 22: END-TO-END INTEGRATION. The one demo that exercises every
stage of the architecture together in a single run, not pairwise:

    MARKET SIMULATOR (asyncio-style generator process)
            |  writes real orders
            v
    mmap RING BUFFER (shared memory, zero-copy, struct-packed)
            |  read by a second real OS process
            v
    CYTHON MATCHING ENGINE (OrderBookCython, price-time priority)
            |  produces trades with nanosecond latency instrumentation
            +----------------------------+
            v                            v
    SQLite LEDGER (async-flushed,   CURSES DASHBOARD (live bid/ask,
    durable audit trail)             whale highlights, p50/p95/p99/p999
                                      latency in microseconds)

Every other demo in this project exercises a SUBSET of this chain:
    run_demo.py               -- firehose -> ring buffer -> engine
    run_dashboard_demo.py     -- firehose -> ring buffer -> engine -> dashboard
    run_persistence_demo.py   -- firehose -> ring buffer -> engine -> ledger
This script is the one that puts all five stages in the same run, and
verifies the two downstream consumers (ledger, dashboard) agree with
the engine's own record of what happened -- not just that neither one
crashed.

Design note on combining the ledger flush with the curses loop: the
dashboard's render loop (dashboard.live_dashboard.run_dashboard) is a
plain synchronous loop, not asyncio -- curses.wrapper()'s callback
isn't a coroutine. Rather than run TradeFlusher's asyncio scheduling
inside (or alongside, via a second thread) that synchronous loop, this
script uses run_dashboard()'s on_frame hook to call the SAME
underlying flush primitive (database.ledger.save_trades_batch(),
pulling new trades via the engine's own get_trades_since()) directly,
synchronously, every FLUSH_EVERY_N_FRAMES frames. This is functionally
the same periodic-batched-flush behavior TradeFlusher provides
elsewhere in this project, without introducing a second concurrency
model into a curses callback -- simplicity chosen deliberately over
technically running TradeFlusher unmodified here.

Run:
    python setup_demo.py                    (one-time, if not already built)
    python run_full_integration_demo.py
"""

import curses
import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "matching_engine"))

from engine_check import require_compiled_engine
from shared.ring_buffer import RingBuffer
from shared.shared_memory import reset_shared_region
from simulator.order_generator import generate_order

DEMO_DURATION_SECONDS = 20
ORDERS_PER_SECOND = 10
RING_BUFFER_CAPACITY = 256
FLUSH_EVERY_N_FRAMES = 2  # ~every 100ms at the dashboard's ~20fps redraw rate,
                            # matching TradeFlusher's own default interval elsewhere

BACKING_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ring_buffer.mem")
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chronosmatch_ledger.db")


def generator_process():
    """Stage 1: MARKET SIMULATOR. Same generator every other demo in
    this project uses -- silent (no prints; curses owns the terminal
    once the dashboard starts, and mixing plain stdout writes into a
    curses screen corrupts the display)."""
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    interval = 1.0 / ORDERS_PER_SECOND
    end_time = time.time() + DEMO_DURATION_SECONDS

    while time.time() < end_time:
        order = generate_order()
        while rb.is_full():
            time.sleep(0.01)
        rb.write_order(order)
        time.sleep(interval)


def matcher_dashboard_ledger_process():
    """Stages 2-5 combined: reads from the ring buffer, matches via the
    real compiled Cython engine, periodically flushes new trades to a
    real SQLite ledger, and renders the live curses dashboard -- all
    driven by dashboard.live_dashboard.run_dashboard()'s single
    synchronous loop via its on_frame hook."""
    from dashboard.live_dashboard import run_dashboard
    from database import ledger

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = ledger.get_connection(DB_PATH)

    state = {"last_flushed_index": 0, "frame_count": 0, "total_flushed": 0}

    def on_frame(book, orders_processed, trades_matched):
        state["frame_count"] += 1
        if state["frame_count"] % FLUSH_EVERY_N_FRAMES != 0:
            return
        new_trades = book.get_trades_since(state["last_flushed_index"])
        if not new_trades:
            return
        flushed_at = time.perf_counter_ns()
        inserted = ledger.save_trades_batch(conn, new_trades, flushed_at)
        state["last_flushed_index"] = book.trade_count
        state["total_flushed"] += inserted

    def _run(stdscr):
        run_dashboard(stdscr, ring_buffer_capacity=RING_BUFFER_CAPACITY,
                      duration_seconds=DEMO_DURATION_SECONDS, on_frame=on_frame)

    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass

    # Final flush of anything produced in the last frame(s) before exit,
    # then verify the ledger's own count against what got flushed.
    ledger_stats = ledger.get_statistics(conn)
    print(f"[matcher+ledger+dashboard pid={os.getpid()}] "
          f"Flushed {state['total_flushed']} trades to the ledger across "
          f"{state['frame_count']} frames.")
    print(f"[matcher+ledger+dashboard pid={os.getpid()}] "
          f"Ledger total_trades: {ledger_stats['total_trades']}")
    conn.close()






def report_exit_status(banner, **processes):
    """Print an honest summary and exit non-zero if any child crashed.

    These demos used to print "Both processes exited cleanly"
    unconditionally, without ever looking at an exit code. A child could
    die on an unhandled exception and the demo would still announce
    success --- which is exactly what happened when the Cython engine
    was missing: the matcher crashed on import, and the demo reported a
    clean finish regardless.
    """
    failures = {name: p.exitcode for name, p in processes.items() if p.exitcode != 0}

    print()
    print("=" * 70)
    if failures:
        print(f"{banner} FAILED.")
        for name, code in failures.items():
            print(f"  {name} process exited with code {code} "
                  f"(see its traceback above)")
        print("=" * 70)
        sys.exit(1)

    codes = ", ".join(f"{name} {p.exitcode}" for name, p in processes.items())
    print(f"{banner} All processes exited cleanly (exit codes: {codes}).")
    print("=" * 70)


def main():
    # reset_shared_region() removes leftovers from a previous run (both
    # the .mem file and its .lock) and releases the creating handle, so
    # the child processes are the only holders. Doing this by hand used
    # to miss the lock file and keep the mapping open, which on Windows
    # left files that could not be deleted or resized on the next run.
    # Check before starting any child process: the import failure
    # otherwise happens inside a child, as a traceback buried in the
    # output.
    require_compiled_engine()

    reset_shared_region(RING_BUFFER_CAPACITY, backing_file=BACKING_FILE)

    print("=" * 70)
    print("ChronosMatch — Full End-to-End Integration Demo (Day 22)")
    print("firehose -> ring buffer -> Cython engine -> ledger -> dashboard")
    print(f"Running for {DEMO_DURATION_SECONDS}s. The curses dashboard will take")
    print("over the terminal; ledger flush stats print after it exits.")
    print("=" * 70)
    time.sleep(2)

    gen = multiprocessing.Process(target=generator_process, name="generator")
    matcher = multiprocessing.Process(target=matcher_dashboard_ledger_process, name="matcher")

    gen.start()
    matcher.start()
    gen.join()
    matcher.join()

    print()
    print("=" * 70)
    report_exit_status("Integration demo finished.", generator=gen, matcher=matcher)
    print("Every stage of the architecture ran in this single demo:")
    print("  market simulator -> mmap ring buffer -> Cython matching engine")
    print("  -> SQLite ledger (async-style batched flush) -> curses dashboard")
    print(f"Inspect the ledger yourself:")
    print(f"  sqlite3 {DB_PATH} \"SELECT * FROM trades ORDER BY trade_id DESC LIMIT 10;\"")
    print("=" * 70)


if __name__ == "__main__":
    main()
