"""
simulator/order_generator.py
------------------------------
MEMBER B'S ORDER GENERATION LOGIC.

Day 2: pure order generation --- builds a single random order dict
following the agreed shared format. Does NOT talk to the ring buffer
yet; that wiring (start_simulation/stop/pause/resume calling
write_order()) lands in market_simulator.py (Day 4).

Order format (agreed with Member A / Leader):
{
    "order_id": int,
    "side": "B" or "S",
    "price": float,
    "quantity": int,
    "timestamp": int,
}
"""

import random
import time

from simulator import config

_next_order_id = 1


def next_order_id() -> int:
    """Monotonically increasing order id. Not thread-safe by itself ---
    market_simulator.py is responsible for serializing calls to this
    if it ever runs generate_order() from more than one thread."""
    global _next_order_id
    order_id = _next_order_id
    _next_order_id += 1
    return order_id


def generate_order() -> dict:
    """Build one random order using the ranges in config.py."""
    side = "B" if random.random() < config.BUY_PROBABILITY else "S"
    price = round(random.uniform(config.PRICE_MIN, config.PRICE_MAX), 2)
    quantity = random.randint(config.MIN_QUANTITY, config.MAX_QUANTITY)

    return {
        "order_id": next_order_id(),
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": time.perf_counter_ns(),
    }


if __name__ == "__main__":
    # Manual smoke test: generate a handful of orders and print them.
    for _ in range(5):
        print(generate_order())
