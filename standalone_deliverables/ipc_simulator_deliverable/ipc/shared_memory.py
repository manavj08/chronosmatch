"""
ipc/shared_memory.py
-----------------------
Manages a memory-mapped (mmap) region shared across independently-started
OS processes -- the "zero-copy IPC bus" layer. No sockets, no pipes for
the data itself: two processes that open the same backing file path see
the exact same bytes at the exact same (process-relative) memory address.

Layout: [ HEADER (24 bytes) ][ SLOT 0 ][ SLOT 1 ] ... [ SLOT N-1 ]

Header fields (see HEADER_FORMAT below):
    capacity        -- max number of order slots (fixed at creation)
    read_pointer    -- consumer position: index of the next slot to read
    write_pointer   -- producer position: index of the next slot to write
    occupancy       -- number of currently-filled slots (0..capacity)

Each SLOT is exactly protocol.SLOT_SIZE bytes (see protocol.py) -- one
packed Order, no delimiters needed since every slot is the same size.

Synchronization
================
`multiprocessing.Lock()` does NOT work for this: it only synchronizes
processes that share the same Lock *object* (passed explicitly, or
inherited via fork from a common parent). Here, every process
independently constructs its own SharedRingMemory by opening the same
backing file path -- each would get its own separate Lock instance,
providing zero real mutual exclusion. This was a real bug, found under
load: concurrent read/write header updates raced and orders vanished
silently (no exception, no crash -- just gone).

Fixed with genuine OS-native advisory file locking on an open file
descriptor (fcntl.flock on POSIX, msvcrt.locking on Windows), which is
identified by a shared file *path*, not a shared Python object, so it
works correctly across any number of independently-started processes.
It also auto-releases if a process crashes while holding it -- the OS
drops the lock when the file descriptor closes.

The current design uses ONE lock protecting both read_order() and
write_order() -- correct and simple, at the cost of serializing producer
and writer through a single mutex rather than allowing true concurrent
single-producer/single-consumer access. See ring_buffer.py's docstring
for the honest trade-off note.
"""

import mmap
import os
import struct
import sys

from ipc.protocol import SLOT_SIZE

HEADER_FORMAT = "<IIII"  # capacity, read_pointer, write_pointer, occupancy
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

DEFAULT_CAPACITY = 1024
BACKING_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ipc_ring_buffer.mem"
)
LOCK_FILE = BACKING_FILE + ".lock"

if sys.platform == "win32":
    import msvcrt

    def _lock_fd(fd):
        # msvcrt.locking operates on the current file position; lock a
        # single byte at the start of the file as a mutex flag.
        os.lseek(fd, 0, os.SEEK_SET)
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                pass  # someone else holds it; spin and retry

    def _unlock_fd(fd):
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_fd(fd):
        fcntl.flock(fd, fcntl.LOCK_EX)  # blocking exclusive lock; the OS
                                          # handles the wait efficiently,
                                          # no busy-spin needed on POSIX

    def _unlock_fd(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


class CrossProcessLock:
    """
    A mutex identified by a file PATH, not a Python object -- works
    correctly across any number of independently-started OS processes
    that each open the same path, unlike `multiprocessing.Lock()`.
    """

    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        # Open once, kept open for the life of this object -- locking an
        # already-open fd is fast; opening a fresh fd per acquire/release
        # would reintroduce real per-call filesystem overhead.
        self._fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)

    def __enter__(self):
        _lock_fd(self._fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _unlock_fd(self._fd)
        return False

    def close(self):
        os.close(self._fd)


class SharedRingMemory:
    """Owns the mmap region itself: header read/write, slot read/write,
    and the cross-process lock. RingBuffer (ring_buffer.py) builds the
    actual circular-queue semantics (wrap-around, full/empty checks) on
    top of this."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY, create: bool = False,
                 backing_file: str = None):
        """
        Open (or create) the shared memory region.

        Args:
            capacity: max number of order slots in the buffer.
            create: True to initialize a fresh region (first process to
                    start should use this); False to attach to an
                    already-existing region.
            backing_file: override the default backing file path (mainly
                    for tests that want an isolated region).
        """
        self.capacity = capacity
        self.total_size = HEADER_SIZE + (capacity * SLOT_SIZE)
        self.backing_file = backing_file or BACKING_FILE
        self.lock_file = self.backing_file + ".lock"
        self.lock = CrossProcessLock(self.lock_file)

        file_exists = os.path.exists(self.backing_file)

        if create or not file_exists:
            with open(self.backing_file, "wb") as f:
                f.write(b"\x00" * self.total_size)

        self._file = open(self.backing_file, "r+b")
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
        self.mm[offset: offset + SLOT_SIZE] = data

    def read_slot(self, index: int) -> bytes:
        """Read raw bytes from slot `index`."""
        offset = self.slot_offset(index)
        return bytes(self.mm[offset: offset + SLOT_SIZE])

    def close(self):
        """Release the mmap and close the backing file (does not delete
        the backing file itself -- other processes may still be using
        it)."""
        self.mm.close()
        self._file.close()
        self.lock.close()
