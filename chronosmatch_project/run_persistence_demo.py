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

from shared.ring_buffer import RingBuffer
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


def main():
    backing_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ring_buffer.mem")
    if os.path.exists(backing_file):
        os.remove(backing_file)

    RingBuffer(capacity=RING_BUFFER_CAPACITY, create=True)

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

    print()
    print("=" * 70)
    print("Demo finished. Inspect the ledger yourself:")
    print(f"  sqlite3 {DB_PATH} \"SELECT * FROM trades LIMIT 10;\"")
    print("=" * 70)


if __name__ == "__main__":
    main()
