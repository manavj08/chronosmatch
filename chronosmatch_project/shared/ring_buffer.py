from shared.shared_memory import SharedRingMemory
from shared.serializer import serialize, deserialize


class RingBuffer:
    """
    Circular queue for orders, built on top of SharedRingMemory.

    All real state (pointers, occupancy) lives in shared memory, so
    multiple processes using the same backing file see the same buffer.

    Owns OS resources (a memory mapping and a lock file descriptor),
    so it must be closed when you are done with it. Either call
    close() or use it as a context manager:

        with RingBuffer(capacity=1024, create=True) as rb:
            rb.write_order(order)
    """

    def __init__(self, capacity: int = 1024, create: bool = False, backing_file: str | None = None):
        self.mem = SharedRingMemory(
            capacity=capacity, create=create, backing_file=backing_file
        )

    @property
    def backing_file(self) -> str:
        """Path of the mmap file this buffer is attached to."""
        return self.mem.backing_file

    @property
    def lock_file(self) -> str:
        """Path of the lock file guarding this buffer."""
        return self.mem.lock_file

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
            self.mem.update_header(read_ptr, new_write_ptr, occupancy + 1, capacity)

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
            self.mem.update_header(new_read_ptr, write_ptr, occupancy - 1, capacity)

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

    def close(self):
        """Release the underlying shared memory and lock handles.

        Idempotent. Day 9: added because nothing used to release the
        lock file descriptor, which on Windows made the lock file
        undeletable and broke every test that cleaned up after itself.
        """
        self.mem.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False
