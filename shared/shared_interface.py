import mmap
import os
import struct
from multiprocessing import Lock

from shared.serializer import SLOT_SIZE

HEADER_FORMAT = "<IIII"  # capacity, read_pointer, write_pointer, occupancy
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

DEFAULT_CAPACITY = 1024
BACKING_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ring_buffer.mem"
)


class SharedRingMemory:
    """
    Manages a memory-mapped (mmap) region shared across processes.

    Layout: [ HEADER (16 bytes) ][ SLOT 0 ][ SLOT 1 ] ... [ SLOT N-1 ]
    Header stores: capacity, read_pointer, write_pointer, occupancy.
    """

    def __init__(self, capacity: int = DEFAULT_CAPACITY, create: bool = False):
        """
        Open (or create) the shared memory region.

        Args:
            capacity: max number of order slots in the buffer.
            create: True to initialize a fresh region (first process
                    to start should use this); False to attach to an
                    already-existing region.
        """
        self.capacity = capacity
        self.total_size = HEADER_SIZE + (capacity * SLOT_SIZE)
        self.lock = Lock()

        file_exists = os.path.exists(BACKING_FILE)

        if create or not file_exists:
            with open(BACKING_FILE, "wb") as f:
                f.write(b"\x00" * self.total_size)

        self._file = open(BACKING_FILE, "r+b")
        self.mm = mmap.mmap(self._file.fileno(), self.total_size)

        if create or not file_exists:
            self._write_header(capacity=capacity, read_ptr=0, write_ptr=0, occupancy=0)

    def _write_header(self, capacity, read_ptr, write_ptr, occupancy):
        """Internal: pack and write the 4-field header into the mmap."""
        packed = struct.pack(HEADER_FORMAT, capacity, read_ptr, write_ptr, occupancy)
        self.mm[0:HEADER_SIZE] = packed

    def read_header(self):
        """Return the current (capacity, read_ptr, write_ptr, occupancy)."""
        packed = self.mm[0:HEADER_SIZE]
        return struct.unpack(HEADER_FORMAT, packed)

    def update_header(self, read_ptr, write_ptr, occupancy):
        """Update the mutable header fields (capacity never changes)."""
        capacity, _, _, _ = self.read_header()
        self._write_header(capacity, read_ptr, write_ptr, occupancy)

    def slot_offset(self, index: int) -> int:
        """Return the byte offset in the mmap where slot `index` begins."""
        return HEADER_SIZE + (index * SLOT_SIZE)

    def write_slot(self, index: int, data: bytes):
        """Write raw bytes into slot `index`."""
        offset = self.slot_offset(index)
        self.mm[offset : offset + SLOT_SIZE] = data

    def read_slot(self, index: int) -> bytes:
        """Read raw bytes from slot `index`."""
        offset = self.slot_offset(index)
        return bytes(self.mm[offset : offset + SLOT_SIZE])

    def close(self):
        """Release the mmap and close the backing file."""
        self.mm.close()
        self._file.close()