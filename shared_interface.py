"""
shared_interface.py
--------------------
FAKE / STUB version of the IPC bus.

This is the contract every module codes against on Day 1.
Member A will REPLACE the body of these functions with real
mmap + struct code later --- but the function names, arguments,
and return values below must NOT change, or everyone else's
code breaks.

Order format (agreed Day 1):
    order_id : int
    side : "B" for Buy, "S" for Sell
    price : float
    quantity : int
    timestamp : int (nanoseconds, from time.perf_counter_ns())

Trade format (produced by the Order Book, agreed Day 1):
    trade_id : int
    buy_order_id : int
    sell_order_id : int
    price : float
    quantity : int
    matched_at : int (nanoseconds)
"""

import itertools

# ---- FAKE storage (Member A will replace this with real mmap memory) ----
_fake_buffer = []
_order_id_counter = itertools.count(1)


def next_order_id() -> int:
    """Helper so every producer gets a unique order id."""
    return next(_order_id_counter)


def write_order(order: dict) -> None:
    """
    Write one order into the shared bus.

    STUB BEHAVIOR: appends to an in-memory Python list.
    REAL BEHAVIOR (Member A, later): pack the dict with `struct`
    and write the bytes into the mmap ring buffer at the current
    write-pointer slot, then advance the pointer.

    order must contain exactly these keys:
        order_id, side, price, quantity, timestamp
    """
    required = {"order_id", "side", "price", "quantity", "timestamp"}
    if not required.issubset(order):
        raise ValueError(f"order missing required keys: {required - set(order)}")
    _fake_buffer.append(dict(order))


def read_order() -> dict | None:
    """
    Read the next available order from the shared bus.

    STUB BEHAVIOR: pops the oldest order from the in-memory list.
    Returns None if nothing is available (caller should handle this,
    e.g. sleep briefly and retry).

    REAL BEHAVIOR (Member A, later): read record_size bytes from the
    current read-pointer slot in the mmap buffer, unpack with `struct`,
    advance the pointer, return the same dict shape.
    """
    if not _fake_buffer:
        return None
    return _fake_buffer.pop(0)


def buffer_size() -> int:
    """Debug helper: how many orders are currently waiting to be read."""
    return len(_fake_buffer)
