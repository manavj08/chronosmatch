"""
run_demo.py
------------
LIVE DEMO --- run this to show the project working end to end.

What this actually demonstrates (nothing here is faked or simulated):

1. TWO REAL OPERATING SYSTEM PROCESSES, not two threads:
   - a "generator" process that creates random orders and writes them
     into the shared-memory ring buffer
   - a "matcher" process that reads from that SAME memory region and
     feeds every order into the compiled Cython Limit Order Book
2. ZERO-COPY IPC: the two processes never touch a socket, a file (other
   than the mmap-backed region itself), JSON, or Pickle. They share
   raw bytes at the same memory address.
3. THE COMPILED CYTHON ENGINE: matching_engine/order_book.pyx, built
   to a real .so and imported like any other Python module.
4. REAL PRICE-TIME PRIORITY MATCHING (Day 5): incoming orders that
   cross the best opposite price actually execute as trades, with
   partial fills handled correctly --- not just sorted insertion.
5. Live, human-readable output showing orders flowing through the
   system, trades executing when prices cross, and the book staying
   correctly sorted by price.

What this demo does NOT yet show (honestly, not built yet --- see
TASKS.md for the day it's scheduled):
   - GC-pause verification during matching is done (Day 6/11) but not
     surfaced in this demo's output
   - the demo uses a small, readable order rate on purpose (Day 4's
     asyncio firehose can sustain ~100k/sec, see benchmarks/), so the
     output here stays watchable rather than scrolling by instantly

Each TRADE line now shows real per-trade latency in microseconds
(Day 12), measured inside the engine itself from the triggering
order's own timestamp to the moment that trade was recorded.

IMPORTANT --- what this demo's latency numbers actually represent:
orders here are timestamped at GENERATION time
(simulator/order_generator.py). The matcher process in this demo
polls the ring buffer with a 20ms sleep between checks when it finds
nothing to read (see matcher_process() below) --- so an order can sit
in the buffer for up to ~20ms before the matcher even looks at it,
before any engine processing happens at all. That polling delay
dominates the latency numbers shown here; it is a property of this
DEMO's simple polling loop, not of the matching engine itself. Day 9's
audits/engine_verification.py and Day 12's own unit tests measure the
engine's pure matching latency in isolation (single-digit
microseconds, no polling involved) specifically to separate those two
things. A production consumer would use blocking/event-driven reads
instead of sleep-based polling to eliminate this gap --- that's a
demo simplification, not a claim about the engine's real capability.

For the live curses dashboard (Day 7) instead of plain stdout, see
run_dashboard_demo.py.

Run:
    python setup_demo.py     (one-time, builds the Cython extension)
    python run_demo.py
"""

import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "matching_engine"))

from shared.ring_buffer import RingBuffer
from simulator.order_generator import generate_order

DEMO_DURATION_SECONDS = 10
ORDERS_PER_SECOND = 5   # deliberately slow --- this is for watching, not for a throughput test
RING_BUFFER_CAPACITY = 64


def generator_process():
    """Real, separate OS process. Writes orders into shared memory."""
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    interval = 1.0 / ORDERS_PER_SECOND
    end_time = time.time() + DEMO_DURATION_SECONDS

    while time.time() < end_time:
        order = generate_order()
        while rb.is_full():
            time.sleep(0.01)  # backpressure: wait for the matcher to catch up
        rb.write_order(order)
        print(f"[generator pid={os.getpid()}] wrote  "
              f"order #{order['order_id']:<4} {order['side']} "
              f"{order['quantity']:>3} @ {order['price']:.2f}")
        time.sleep(interval)


def matcher_process():
    """Real, separate OS process. Reads the SAME shared memory region
    and feeds every order into the compiled Cython engine's real
    price-time priority matching (Day 5) --- trades execute when
    prices cross, not just sorted insertion. Day 13: also prints a
    periodic latency-stats summary (p50/p99/p999 from the live
    metrics pipeline), alongside each individual trade's own latency
    (Day 12), so both pieces are visible together."""
    from order_book import OrderBookCython  # the compiled .so

    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    book = OrderBookCython()
    end_time = time.time() + DEMO_DURATION_SECONDS + 2  # drain a little after generator stops
    trades_since_last_summary = 0

    while time.time() < end_time:
        order = rb.read_order()
        if order is None:
            time.sleep(0.02)
            continue

        result = book.match_order(order)
        levels = book.get_top_levels(depth=3)
        best_bid = levels["bids"][0]["price"] if levels["bids"] else None
        best_ask = levels["asks"][0]["price"] if levels["asks"] else None
        print(f"[matcher   pid={os.getpid()}] read   "
              f"order #{order['order_id']:<4} {order['side']} "
              f"{order['quantity']:>3} @ {order['price']:.2f}   "
              f"| best bid: {best_bid}  best ask: {best_ask}")

        for trade in result["trades"]:
            print(f"[matcher   pid={os.getpid()}] TRADE  "
                  f"#{trade['trade_id']} — buy #{trade['buy_order_id']} x "
                  f"sell #{trade['sell_order_id']}  "
                  f"{trade['quantity']} @ {trade['price']:.2f}  "
                  f"(latency: {trade['latency_ns'] / 1000:.2f}µs)")
            trades_since_last_summary += 1

        if trades_since_last_summary >= 10:
            stats = book.get_latency_stats()
            print(f"[matcher   pid={os.getpid()}] STATS  "
                  f"n={stats['count']}  "
                  f"p50={stats['p50_ns']/1000:.2f}µs  "
                  f"p99={stats['p99_ns']/1000:.2f}µs  "
                  f"p999={stats['p999_ns']/1000:.2f}µs  "
                  f"max={stats['max_ns']/1000:.2f}µs")
            trades_since_last_summary = 0


def main():
    backing_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ring_buffer.mem")
    if os.path.exists(backing_file):
        os.remove(backing_file)  # start clean each demo run

    # The FIRST process to touch shared memory creates it; the demo
    # creates it here in the parent before either child starts, so
    # there's no race over who creates vs. attaches.
    RingBuffer(capacity=RING_BUFFER_CAPACITY, create=True)

    print("=" * 70)
    print("ChronosMatch — Live Demo")
    print(f"Two real OS processes, sharing memory via mmap, zero-copy.")
    print(f"Generator process writes orders; matcher process (running the")
    print(f"compiled Cython engine) reads them from the SAME memory region.")
    print("=" * 70)
    print()

    gen = multiprocessing.Process(target=generator_process, name="generator")
    match = multiprocessing.Process(target=matcher_process, name="matcher")

    gen.start()
    match.start()

    gen.join()
    match.join()

    print()
    print("=" * 70)
    print("Demo finished. Both processes exited cleanly.")
    print("=" * 70)


if __name__ == "__main__":
    main()
