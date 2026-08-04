"""
ring_buffer_stub.py
--------------------
MEMBER A'S STARTING POINT.

shared_interface.py already contains the FAKE write_order()/read_order()
that the rest of the team is using today. Your job is NOT to write those
from scratch --- it's to replace their insides with real mmap + struct
code, while keeping the exact same function names and behavior.

This file shows you the real struct layout you'll build toward, plus a
minimal working mmap example so you can start immediately without
waiting on anyone.
"""

import struct
import mmap

# ----------------------------------------------------------------------
# Step 1 (Day 1-2): agree on and test the byte layout for one order.
#
# Fields, in order: order_id | side | price | quantity | timestamp
# struct format string: i | c | f | i | q
#   i = int (4 bytes)     c = char (1 byte)     f = float (4 bytes)
#   q = long long (8 bytes, big enough for nanosecond timestamps)
# ----------------------------------------------------------------------
ORDER_FORMAT = "icfiq"
RECORD_SIZE = struct.calcsize(ORDER_FORMAT)  # confirm this prints a sane number
print(f"One order record = {RECORD_SIZE} bytes")


def pack_order(order: dict) -> bytes:
    """Convert an order dict into fixed-size bytes."""
    side_byte = order["side"].encode("ascii")  # "B" or "S" -> b"B"/b"S"
    return struct.pack(
        ORDER_FORMAT,
        order["order_id"],
        side_byte,
        order["price"],
        order["quantity"],
        order["timestamp"],
    )


def unpack_order(data: bytes) -> dict:
    """Convert fixed-size bytes back into an order dict."""
    order_id, side_byte, price, quantity, timestamp = struct.unpack(ORDER_FORMAT, data)
    return {
        "order_id": order_id,
        "side": side_byte.decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
    }


# ----------------------------------------------------------------------
# Step 2 (Day 2-3): minimal single-process mmap example.
# Run this file directly to see it work end-to-end on your machine.
# ----------------------------------------------------------------------
def demo_single_process():
    capacity = 100  # number of order slots
    total_size = RECORD_SIZE * capacity

    # anonymous mmap = memory shared only within THIS process for now.
    # Day 3: switch this to a named, file-backed mmap so a SECOND
    # process can open the same region by filename.
    buf = mmap.mmap(-1, total_size)
    write_ptr = 0

    def write_order_real(order: dict):
        nonlocal write_ptr
        offset = (write_ptr % capacity) * RECORD_SIZE
        buf.seek(offset)
        buf.write(pack_order(order))
        write_ptr += 1

    def read_order_real(index: int) -> dict:
        offset = (index % capacity) * RECORD_SIZE
        buf.seek(offset)
        data = buf.read(RECORD_SIZE)
        return unpack_order(data)

    # quick smoke test
    import time
    test_order = {"order_id": 1, "side": "B", "price": 101.25,
                   "quantity": 10, "timestamp": time.perf_counter_ns()}
    write_order_real(test_order)
    result = read_order_real(0)
    assert result == test_order, f"Mismatch! wrote {test_order} read {result}"
    print("Single-process mmap round-trip OK:", result)


if __name__ == "__main__":
    demo_single_process()

# ----------------------------------------------------------------------
# WHAT TO DO NEXT (after this demo works):
#
# 1. Wrap write_order_real/read_order_real with a real ring buffer
#    (wraparound + a header region storing write_ptr/read_ptr so BOTH
#    processes see the same pointers).
# 2. Replace the fake write_order()/read_order() bodies in
#    shared_interface.py with calls into your real implementation.
#    Do NOT rename them --- the Leader, Member B, and Member C are all
#    importing write_order/read_order from shared_interface.py already.
# 3. Day 3: switch mmap.mmap(-1, ...) to a named/file-backed mmap so a
#    second real OS process (not just this script) can attach to it.
# ----------------------------------------------------------------------
