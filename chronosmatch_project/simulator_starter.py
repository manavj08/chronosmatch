"""
simulator_starter.py
---------------------
MEMBER B'S STARTING POINT.

Generates random Buy/Sell orders and pushes them into the shared bus.
Uses the STUB write_order() from shared_interface.py today --- no
changes needed here on Day 4 when Member A's real buffer goes live,
since you're already calling the shared function, not the internals.
"""

import asyncio
import random
import time

from shared_interface import write_order, next_order_id

BASE_PRICE = 100.0
ORDERS_PER_SECOND = 5  # start small; ramp this up later (Day 6 stress mode)


def make_random_order() -> dict:
    """Build one fake order with a small random walk around BASE_PRICE."""
    side = random.choice(["B", "S"])
    price = round(BASE_PRICE + random.uniform(-1.0, 1.0), 2)
    quantity = random.randint(1, 100)
    return {
        "order_id": next_order_id(),
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


async def run_simulator():
    sent = 0
    interval = 1.0 / ORDERS_PER_SECOND
    start = time.time()

    while True:
        order = make_random_order()
        write_order(order)
        sent += 1

        # Simple throughput readout once a second
        if time.time() - start >= 1.0:
            print(f"Orders sent this second: {sent}")
            sent = 0
            start = time.time()

        await asyncio.sleep(interval)


if __name__ == "__main__":
    print(f"Starting simulator at ~{ORDERS_PER_SECOND} orders/sec (Ctrl+C to stop)")
    try:
        asyncio.run(run_simulator())
    except KeyboardInterrupt:
        print("\nSimulator stopped.")

# ----------------------------------------------------------------------
# WHAT TO DO NEXT:
#
# Day 2 -> add a running orders/sec counter (done above, refine as needed)
#          and make price movement feel more realistic if you want.
# Day 3 -> confirm you can sustain ~100 orders/sec reliably.
# Day 4 -> NOTHING changes here --- Member A's real buffer replaces the
#          stub inside shared_interface.py, and you keep calling
#          write_order() exactly as you already do.
# Day 6 -> add a stress mode: a CLI flag or constant that ramps
#          ORDERS_PER_SECOND up (100 -> 1000 -> 10000) to find limits.
# Day 7 -> start the SQLite persistence layer (separate file), using a
#          hand-made fake trade dict first, before wiring to real trades.
# ----------------------------------------------------------------------
