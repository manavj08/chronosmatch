import mmap
import os
import struct
import sys

from shared.serializer import SLOT_SIZE

HEADER_FORMAT = "<IIII"  # capacity, read_pointer, write_pointer, occupancy
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)

DEFAULT_CAPACITY = 1024
BACKING_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ring_buffer.mem"
)
LOCK_FILE = BACKING_FILE + ".lock"

# Day 8 fix, take 2: the first fix attempt (see _CrossProcessLock's
# docstring below for the full history) used atomic file CREATE/DELETE
# That was correct but slow --- ~34,700 write+read cycles/sec in a
# single-process timing test, and the real two-process 1,000,000-order
# audit did not finish within a 180-second timeout, almost certainly
# from lock contention (two processes constantly racing to
# create/delete the same lock file is expensive: real filesystem
# syscalls, not just memory operations). Replaced with genuine
# OS-native advisory file locking on an already-open file descriptor
# --- fcntl.flock on POSIX, msvcrt.locking on Windows --- which locks
# and unlocks an existing fd instead of creating/deleting a file each
# time, and is the standard, fast, atomic tool for exactly this job
# on each respective platform.
if sys.platform == "win32":
    import msvcrt

    def _lock_fd(fd):
        # msvcrt.locking operates on the current file position; lock
        # a single byte at the start of the file as a mutex flag.
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
        fcntl.flock(fd, fcntl.LOCK_EX)  # blocking exclusive lock;
                                          # the OS handles the wait
                                          # efficiently, no busy-spin
                                          # needed on POSIX

    def _unlock_fd(fd):
        fcntl.flock(fd, fcntl.LOCK_UN)


class _CrossProcessLock:
    """
    Day 8 fix for a real bug found during the Mid-Project Review IPC
    audit: `multiprocessing.Lock()` only synchronizes processes that
    SHARE the same Lock object (e.g. passed explicitly via
    Process(args=...) or inherited through fork from a common
    parent). Every process in this project independently constructs
    its own RingBuffer()/SharedRingMemory() by opening the same
    BACKING_FILE path --- each one was getting its OWN separate
    Lock() instance, providing zero actual cross-process mutual
    exclusion. Under concurrent load (audits/ipc_audit.py, 1,000,000
    orders) this caused silent data loss: the read/write header
    updates raced, and about 30% of orders vanished without any
    error, exception, or crash --- just gone.

    First fix attempt used atomic file create/delete (os.O_CREAT |
    O_EXCL) as the lock primitive --- correct, but slow: ~34,700
    write+read cycles/sec in a single-process timing test, and the
    real two-process 1,000,000-order audit did not finish within a
    180-second timeout, from lock contention (constantly creating and
    deleting a file is real filesystem I/O, not just memory ops).

    This version uses genuine OS-native advisory file locking on an
    already-open file descriptor instead --- fcntl.flock on POSIX,
    msvcrt.locking on Windows --- which is the standard, fast, atomic
    tool for this exact job on each platform, and locks/unlocks an
    existing fd rather than creating/deleting a file each time.
    """

    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        # Open once, kept open for the life of this object --- locking
        # an already-open fd is fast; opening a fresh fd per
        # acquire/release would reintroduce the same per-call
        # filesystem overhead that made the first fix slow.
        self._fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)

    def __enter__(self):
        _lock_fd(self._fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _unlock_fd(self._fd)
        return False


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
        # Day 8 fix: was `self.lock = Lock()` (multiprocessing.Lock),
        # which does NOT synchronize across independently-started
        # processes --- each process attaching to this shared memory
        # got its own separate Lock, providing no real mutual
        # exclusion. See _CrossProcessLock's docstring above for the
        # full story (a real 1,000,000-order audit caught this as
        # silent data loss). Fixed with OS-native file locking, which
        # works correctly across any number of independently-started
        # processes since it's identified by a shared file path, not
        # a shared Python object. Unlike the first (slower) fix
        # attempt using file create/delete, this also auto-releases
        # if a process crashes while holding the lock --- the OS
        # drops the lock when the file descriptor closes, so there's
        # no stale-lock-file cleanup needed here.
        self.lock = _CrossProcessLock(LOCK_FILE)

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