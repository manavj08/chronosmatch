"""
ipc/protocol.py
------------------
Binary wire format for one Order, used on the hot IPC path between the
market simulator (producer) and the matching engine (consumer). No JSON,
no Pickle, no Python dict crosses the shared-memory boundary -- only raw
bytes, packed and unpacked with the standard-library `struct` module.

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

Format string: "<Qcdiq..." -- see FORMAT below. The leading "<" fixes
byte order to little-endian AND disables the platform's native struct
alignment/padding rules, so the 29-byte size above is exact and portable
across machines -- without it, `struct` would insert padding bytes
between fields to satisfy native C alignment (e.g. the `d` field would
get padded to an 8-byte boundary relative to a *native*-mode base),
which would make SLOT_SIZE platform-dependent. Producer and consumer
processes MUST agree on this format string exactly, which is why it is
defined in exactly one place (this module) and imported everywhere else
that needs it (ring_buffer.py, shared_memory.py) rather than being
re-typed.

Why not JSON / Pickle / a Python dict on this path: see
ipc_serialization_comparison.py for a measured comparison. In short,
JSON and Pickle both (a) allocate a new Python object graph on every
single message and (b) run a general-purpose encoder/decoder over that
graph -- work that scales with message complexity and triggers Python's
memory allocator and GC on every call. A fixed-size struct pack/unpack
is a handful of machine instructions operating on primitive C types,
with a size known in advance, so the receiving side doesn't even need
to scan for a delimiter -- it just reads exactly SLOT_SIZE bytes.
"""

import struct

# "<" = little-endian, standard size, no padding (see module docstring).
# Q = unsigned long long (8 bytes) -- order_id
# c = char             (1 byte)  -- side, 'B' or 'S'
# d = double            (8 bytes) -- price
# I = unsigned int      (4 bytes) -- quantity
# Q = unsigned long long (8 bytes) -- timestamp
FORMAT = "<QcdIQ"
SLOT_SIZE = struct.calcsize(FORMAT)
assert SLOT_SIZE == 29, f"protocol layout changed unexpectedly: {SLOT_SIZE} bytes"

_VALID_SIDES = (b"B", b"S")


def pack_order(order: dict) -> bytes:
    """
    Serialize an order dict into a fixed-size 29-byte binary blob.

    Args:
        order: dict with keys order_id (int), side ('B' or 'S'),
               price (float), quantity (int), timestamp (int).

    Returns:
        bytes of length SLOT_SIZE (29).

    Raises:
        struct.error if a field is missing or the wrong type/out of
        range for its wire type (e.g. a negative quantity, which
        doesn't fit in the unsigned 'I' field) -- fails loudly at the
        IPC boundary rather than writing corrupt bytes into shared
        memory that some other process would later misinterpret.
    """
    side_byte = order["side"].encode("ascii") if isinstance(order["side"], str) else order["side"]
    return struct.pack(
        FORMAT,
        order["order_id"],
        side_byte,
        order["price"],
        order["quantity"],
        order["timestamp"],
    )


def unpack_order(binary: bytes) -> dict:
    """
    Deserialize a 29-byte binary blob back into an order dict.

    Args:
        binary: bytes of length SLOT_SIZE, as produced by pack_order().

    Returns:
        dict with keys order_id, side, price, quantity, timestamp,
        with the same types pack_order() accepted.
    """
    order_id, side_byte, price, quantity, timestamp = struct.unpack(FORMAT, binary)
    return {
        "order_id": order_id,
        "side": side_byte.decode("ascii"),
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
    }


# Backwards-compatible aliases matching the shorter names used
# elsewhere in this codebase (shared/serializer.py's public API).
serialize = pack_order
deserialize = unpack_order


if __name__ == "__main__":
    # Manual smoke test + a human-readable dump of the wire layout.
    sample = {"order_id": 42, "side": "B", "price": 101.25, "quantity": 7, "timestamp": 123_456_789}
    blob = pack_order(sample)
    round_tripped = unpack_order(blob)

    print("Binary order protocol")
    print("=" * 60)
    print(f"Format string : {FORMAT!r}")
    print(f"Slot size     : {SLOT_SIZE} bytes")
    print(f"Sample order  : {sample}")
    print(f"Packed bytes  : {blob!r}")
    print(f"Round-tripped : {round_tripped}")
    print(f"Round-trip OK : {round_tripped == sample}")
