from shared.shared_interface import SharedRingMemory
from shared.serializer import serialize, deserialize


class RingBuffer:
    """
    Circular queue for orders, built on top of SharedRingMemory.

    All real state (pointers, occupancy) lives in shared memory, so
    multiple processes using the same backing file see the same buffer.
    """

    def __init__(self, capacity: int = 1024, create: bool = False):
        self.mem = SharedRingMemory(capacity=capacity, create=create)

    def is_empty(self) -> bool:
        """Return True if the buffer currently holds zero orders."""
        capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()
        return occupancy == 0

    def is_full(self) -> bool:
        """Return True if the buffer is at max capacity."""
        capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()
        return occupancy == capacity

    def size(self) -> int:
        """Return the current number of orders in the buffer."""
        capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()
        return occupancy

    def write_order(self, order: dict) -> bool:
        """
        Write an order into the buffer at the write pointer, then
        advance the pointer (wrapping around at capacity).

        Returns:
            True if the order was written; False if the buffer was full.
        """
        with self.mem.lock:
            capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()

            if occupancy == capacity:
                return False

            data = serialize(order)
            self.mem.write_slot(write_ptr, data)

            new_write_ptr = (write_ptr + 1) % capacity
            self.mem.update_header(read_ptr, new_write_ptr, occupancy + 1)

            return True

    def read_order(self):
        """
        Read the oldest order from the buffer at the read pointer, then
        advance the pointer (wrapping around at capacity).

        Returns:
            The order dict, or None if the buffer was empty.
        """
        with self.mem.lock:
            capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()

            if occupancy == 0:
                return None

            data = self.mem.read_slot(read_ptr)
            order = deserialize(data)

            new_read_ptr = (read_ptr + 1) % capacity
            self.mem.update_header(new_read_ptr, write_ptr, occupancy - 1)

            return order

    def get_stats(self) -> dict:
        """Return current buffer stats: capacity, occupancy, and pointers."""
        capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()
        return {
            "capacity": capacity,
            "occupancy": occupancy,
            "read_pointer": read_ptr,
            "write_pointer": write_ptr,
        }