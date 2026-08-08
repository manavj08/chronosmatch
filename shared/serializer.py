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