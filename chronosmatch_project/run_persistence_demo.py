"""
run_persistence_demo.py
---------------------------
Day 14: one-command demo of the async SQLite trade flusher, the same
way run_demo.py and run_dashboard_demo.py demo the matching engine
and the curses dashboard respectively. Kept as its own script rather
than folded into run_demo.py's synchronous matcher loop --- the
flusher is asyncio-based and needs to run in the same process as the
OrderBookCython instance it reads from (trades live in that object's
memory, not in shared memory the way orders do), so this demo's
matcher process runs an asyncio event loop instead of the plain
synchronous loop run_demo.py uses.

What this demonstrates:
- A real generator process writing orders into the shared ring buffer
  (same as run_demo.py)
- A matcher process that both matches orders (Cython engine) AND runs
  the async TradeFlusher concurrently, in the same event loop
- Every trade produced ends up durably persisted in a real SQLite
  file (chronosmatch_ledger.db) --- verified at the end of the run by
  reading it back and comparing against the engine's own trade count

Run:
    python setup_demo.py         (one-time, if not already built)
    python run_persistence_demo.py
"""

import asyncio
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

DEMO_DURATION_SECONDS = 10
ORDERS_PER_SECOND = 8
RING_BUFFER_CAPACITY = 256
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chronosmatch_ledger.db")


def generator_process():
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    interval = 1.0 / ORDERS_PER_SECOND
    end_time = time.time() + DEMO_DURATION_SECONDS

    while time.time() < end_time:
        order = generate_order()
        while rb.is_full():
            time.sleep(0.01)
        rb.write_order(order)
        print(f"[generator pid={os.getpid()}] wrote order #{order['order_id']}")
        time.sleep(interval)


async def matcher_and_flusher_process():
    from order_book import OrderBookCython
    from database import ledger
    from database.trade_flusher import TradeFlusher

    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    book = OrderBookCython()

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = ledger.get_connection(DB_PATH)

    flusher = TradeFlusher(book, conn, flush_interval_seconds=0.1)
    flusher.start()

    end_time = time.time() + DEMO_DURATION_SECONDS + 2

    async def match_loop():
        while time.time() < end_time:
            order = rb.read_order()
            if order is None:
                await asyncio.sleep(0.02)
                continue
            result = book.match_order(order)
            for trade in result["trades"]:
                print(f"[matcher   pid={os.getpid()}] TRADE #{trade['trade_id']} "
                      f"{trade['quantity']} @ {trade['price']:.2f}")

    await match_loop()
    await flusher.stop()

    flusher_stats = flusher.get_stats()
    ledger_stats = ledger.get_statistics(conn)
    print(f"\n[matcher   pid={os.getpid()}] Flusher stats: {flusher_stats}")
    print(f"[matcher   pid={os.getpid()}] Engine trade_count: {book.trade_count}")
    print(f"[matcher   pid={os.getpid()}] Ledger total_trades: {ledger_stats['total_trades']}")

    if book.trade_count == ledger_stats["total_trades"]:
        print(f"[matcher   pid={os.getpid()}] VERIFIED: every engine trade made it into the ledger.")
    else:
        print(f"[matcher   pid={os.getpid()}] MISMATCH: engine and ledger trade counts differ.")

    conn.close()


def matcher_entrypoint():
    asyncio.run(matcher_and_flusher_process())






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

    reset_shared_region(RING_BUFFER_CAPACITY)

    print("=" * 70)
    print("ChronosMatch — Persistence Demo (Day 14)")
    print("Real trades, matched live, asynchronously flushed to a real")
    print(f"SQLite file: {DB_PATH}")
    print("=" * 70)
    print()

    gen = multiprocessing.Process(target=generator_process, name="generator")
    match = multiprocessing.Process(target=matcher_entrypoint, name="matcher")

    gen.start()
    match.start()
    gen.join()
    match.join()

    report_exit_status("Persistence demo finished.", generator=gen, matcher=match)

    print()
    print("=" * 70)
    print("Demo finished. Inspect the ledger yourself:")
    print(f"  sqlite3 {DB_PATH} \"SELECT * FROM trades LIMIT 10;\"")
    print("=" * 70)


if __name__ == "__main__":
    main()
