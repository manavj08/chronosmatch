"""
ipc/ring_buffer.py
---------------------
Single-producer/single-consumer circular queue of Orders, built on top of
SharedRingMemory (shared_memory.py) + the binary wire format
(protocol.py). All real state -- capacity, read/write pointers,
occupancy -- lives IN the shared memory region itself, not in this
Python object, so any number of independently-started processes that
open the same backing file see the exact same buffer state.

Wrap-around: both pointers are indices in [0, capacity), advanced with
modulo arithmetic (`(ptr + 1) % capacity`) -- when a pointer reaches the
last slot, the next advance wraps back to slot 0, reusing the same fixed
block of memory forever rather than growing without bound.

Full-buffer behavior: write_order() checks occupancy == capacity BEFORE
writing and returns False without touching memory if the buffer is
full -- the caller (a firehose, a test, a benchmark) decides whether to
retry, back off, or drop the order. The buffer never overwrites data
that hasn't been read yet.

Empty-buffer behavior: read_order() checks occupancy == 0 and returns
None without touching memory if there's nothing to read -- the caller
decides whether to poll again, sleep, or exit.

Synchronization: every write_order()/read_order() call holds the shared
CrossProcessLock for its entire read-modify-write of the header, so a
concurrent writer and reader (or multiple of either) can never observe a
torn/inconsistent header. See shared_memory.py's docstring for why a
plain multiprocessing.Lock() doesn't work here, and the honest note
below on what this design does and doesn't guarantee.

Design honesty: this is a SINGLE lock shared by both write_order() and
read_order() -- correctness comes from serializing every buffer access
through one mutex, not from a true lock-free SPSC (single-producer/
single-consumer) algorithm using atomic pointer operations. A lock-free
SPSC ring buffer is possible (and would let the producer and consumer
touch the buffer fully concurrently, at the cost of needing real atomic
compare-and-swap primitives, which aren't natively available from pure
Python across independently-started processes without an additional
C extension). This design trades some of that theoretical concurrency
for simplicity and a locking primitive (fcntl.flock / msvcrt.locking)
that's standard, well-understood, and already proven correct under a
real 1,000,000-order two-process audit (see tests/test_ring_buffer.py
and audits/ipc_audit.py).
"""

from ipc.shared_memory import SharedRingMemory
from ipc.protocol import pack_order, unpack_order


class RingBuffer:
    """Circular queue for orders. Every method is safe to call from any
    number of independently-started processes that opened the same
    backing file."""

    def __init__(self, capacity: int = 1024, create: bool = False, backing_file: str = None):
        self.mem = SharedRingMemory(capacity=capacity, create=create, backing_file=backing_file)

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
        Write an order into the buffer at the write pointer (producer
        position), then advance the pointer, wrapping around at
        capacity.

        Returns:
            True if the order was written; False if the buffer was full
            (full-buffer behavior: nothing is written, nothing is
            overwritten, the caller decides what to do next).
        """
        with self.mem.lock:
            capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()

            if occupancy == capacity:
                return False

            data = pack_order(order)
            self.mem.write_slot(write_ptr, data)

            new_write_ptr = (write_ptr + 1) % capacity  # wrap-around
            self.mem.update_header(read_ptr, new_write_ptr, occupancy + 1)

            return True

    def read_order(self):
        """
        Read the oldest order from the buffer at the read pointer
        (consumer position), then advance the pointer, wrapping around
        at capacity.

        Returns:
            The order dict, or None if the buffer was empty
            (empty-buffer behavior: nothing is consumed, the caller
            decides whether to poll again).
        """
        with self.mem.lock:
            capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()

            if occupancy == 0:
                return None

            data = self.mem.read_slot(read_ptr)
            order = unpack_order(data)

            new_read_ptr = (read_ptr + 1) % capacity  # wrap-around
            self.mem.update_header(new_read_ptr, write_ptr, occupancy - 1)

            return order

    def get_stats(self) -> dict:
        """Return current buffer stats: capacity, occupancy, and both
        pointers (producer position = write_pointer, consumer position
        = read_pointer)."""
        capacity, read_ptr, write_ptr, occupancy = self.mem.read_header()
        return {
            "capacity": capacity,
            "occupancy": occupancy,
            "read_pointer": read_ptr,
            "write_pointer": write_ptr,
        }

    def close(self):
        self.mem.close()
