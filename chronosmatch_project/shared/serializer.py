"""
shared/serializer.py
-----------------------
Binary wire format for one Order, used on the hot IPC path between the
market simulator (producer) and the matching engine (consumer). No
JSON, no Pickle, no Python dict crosses the shared-memory boundary --
only raw bytes, packed and unpacked with the standard-library `struct`
module. See benchmarks/serialization_comparison.py for a measured
throughput comparison against JSON/Pickle.

Order
├── Order ID    (order_id)
├── Side        (side)
├── Price       (price)
├── Quantity    (quantity)
└── Timestamp   (timestamp)

Wire layout (29 bytes total, fixed size, every field always present):

    Offset  Size  Field        struct code   Python type   Notes
    ------  ----  -----------  ------------  ------------  --------------------------------
    0       8     order_id     Q             int           unsigned 64-bit, monotonic counter
    8       1     side         c             bytes (len 1) ASCII 'B' or 'S'
    9       8     price        d             float         IEEE-754 double
    17      4     quantity     I             int           unsigned 32-bit
    21      8     timestamp    Q             int           unsigned 64-bit nanoseconds
                                                             (time.perf_counter_ns() scale)
    ------  ----
    Total   29 bytes

The leading "<" in _FORMAT fixes byte order to little-endian AND
disables the platform's native struct alignment/padding rules, so the
29-byte size above is exact and portable across machines -- without it,
`struct` would insert padding bytes between fields to satisfy native C
alignment, making SLOT_SIZE platform-dependent. Producer and consumer
processes must agree on this format exactly, which is why it's defined
in exactly one place (this module) and imported everywhere else that
needs it (shared/shared_memory.py) rather than re-typed.
"""

import struct

_FORMAT = "<Qc d I Q".replace(" ", "")
SLOT_SIZE = struct.calcsize(_FORMAT)


def serialize(order: dict) -> bytes:
    """
    Convert an order dict into a fixed-size binary blob (29 bytes).

    Args:
        order: dict with keys order_id (int), side ('B' or 'S'),
               price (float), quantity (int), timestamp (int).

    Returns:
        bytes of length SLOT_SIZE representing the order.
    """
    side_byte = order["side"].encode("ascii")
    return struct.pack(_FORMAT, order["order_id"], side_byte, order["price"], order["quantity"], order["timestamp"])


def deserialize(binary: bytes) -> dict:
    """
    Convert a fixed-size binary blob back into an order dict.

    Args:
        binary: bytes of length SLOT_SIZE, as produced by serialize().

    Returns:
        dict with the original order fields and types.
    """
    order_id, side_byte, price, quantity, timestamp = struct.unpack(_FORMAT, binary)
    return {
        "order_id": order_id,
        "side": side_byte.decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
    }