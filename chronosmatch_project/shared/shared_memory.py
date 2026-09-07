"""
shared/shared_memory.py
--------------------------
Memory-mapped shared-memory region plus the cross-process lock that
guards it. This is the lowest layer of the IPC bus: RingBuffer sits
on top of it and every process in the project attaches to the same
region by opening the same backing-file path.
"""

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


def lock_path_for(backing_file: str) -> str:
    """The lock file that pairs with a given backing file.

    Kept as a single function so the ".lock" suffix convention lives
    in exactly one place --- tests and audit scripts that clean up
    stale files derive the path from here rather than re-typing it.
    """
    return backing_file + ".lock"


def reset_shared_region(capacity: int, backing_file: str | None = None) -> str:
    """Discard any stale shared region and create a fresh, empty one.

    Every entry point (the demo runners, the audit scripts, the load
    test) needs the same three steps before starting its child
    processes: remove leftovers from a previous run, create the region,
    and then let go of it so the children are the only holders. They
    each used to open-code that, and each of them forgot to release the
    creating handle --- harmless on POSIX, but on Windows a retained
    handle makes the file impossible to delete or resize on the next
    run. Centralizing it here means the cleanup is done once, correctly.

    Returns the backing-file path that was initialized.
    """
    path = backing_file if backing_file is not None else BACKING_FILE

    for stale in (path, lock_path_for(path)):
        try:
            if os.path.exists(stale):
                os.remove(stale)
        except OSError:
            # A live handle from a previous run still holds it. The
            # region gets re-initialized below regardless, so this is
            # not worth failing over.
            pass

    with SharedRingMemory(capacity=capacity, create=True, backing_file=path):
        pass  # create and initialize, then release the handle

    return path


# Day 8 fix, take 2: the first fix attempt (see _CrossProcessLock's
# docstring below for the full history) used atomic file CREATE/DELETE.
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

    # msvcrt.locking() locks bytes starting at the file's CURRENT
    # position and, per the Win32 _locking documentation, does not move
    # it. So a single seek to byte 0 when the lock is opened is enough,
    # and the two os.lseek calls that used to run on every acquire and
    # every release are pure overhead --- four extra syscalls per order
    # round trip on the hottest path in the project.
    #
    # That reasoning is only worth acting on if it is actually true on
    # the machine we are running on, and the failure mode if it is not
    # would be severe: two processes would lock DIFFERENT bytes, which
    # is not an error, just an absence of mutual exclusion --- silent
    # data loss, exactly the Day 8 bug all over again. So rather than
    # trusting the documentation, _CrossProcessLock verifies it once at
    # startup (see _position_is_stable_after_locking) and falls back to
    # seeking every time if the assumption does not hold.

    def _seek_to_lock_byte(fd):
        os.lseek(fd, 0, os.SEEK_SET)

    def _lock_fd(fd, needs_seek=True):
        if needs_seek:
            os.lseek(fd, 0, os.SEEK_SET)
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                pass  # someone else holds it; spin and retry

    def _unlock_fd(fd, needs_seek=True):
        if needs_seek:
            os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)

    def _position_is_stable_after_locking(fd):
        """One lock/unlock cycle, checking the file position survives it.

        Returns True when the position is unchanged, meaning the
        per-call seeks can be skipped. Any surprise --- an unexpected
        position, or an error during the probe --- returns False, and
        the safe per-call seeking is kept.
        """
        try:
            os.lseek(fd, 0, os.SEEK_SET)
            _lock_fd(fd, needs_seek=False)
            after_lock = os.lseek(fd, 0, os.SEEK_CUR)
            _unlock_fd(fd, needs_seek=False)
            after_unlock = os.lseek(fd, 0, os.SEEK_CUR)
            os.lseek(fd, 0, os.SEEK_SET)
            return after_lock == 0 and after_unlock == 0
        except OSError:
            return False
else:
    import fcntl

    def _lock_fd(fd, needs_seek=False):
        fcntl.flock(fd, fcntl.LOCK_EX)  # blocking exclusive lock;
                                        # the OS handles the wait
                                        # efficiently, no busy-spin
                                        # needed on POSIX

    def _unlock_fd(fd, needs_seek=False):
        fcntl.flock(fd, fcntl.LOCK_UN)

    def _position_is_stable_after_locking(fd):
        # flock() ignores the file position entirely, so there is
        # nothing to seek and nothing to probe.
        return True


class _CrossProcessLock:
    """
    Day 8 fix for a real bug found during the Mid-Project Review IPC
    audit: `multiprocessing.Lock()` only synchronizes processes that
    SHARE the same Lock object (e.g. passed explicitly via
    Process(args=...) or inherited through fork from a common
    parent). Every process in this project independently constructs
    its own RingBuffer()/SharedRingMemory() by opening the same
    backing-file path --- each one was getting its OWN separate
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

    Day 9 fix: this class now closes its file descriptor. `os.open`
    returns a raw integer fd, NOT a Python file object --- nothing
    reclaims it automatically, so every SharedRingMemory ever built
    used to leak one open handle on the lock file for the lifetime
    of the process. On POSIX that is invisible (you can unlink a file
    that still has open handles), which is why it went unnoticed. On
    Windows it is fatal: any later attempt to delete the lock file
    fails with WinError 32 ("file is being used by another process").
    A pytest run that builds ~20 RingBuffers therefore leaked ~20
    handles and every cross-process test that cleaned up its backing
    files failed. Hence close(), __del__ as a safety net, and
    context-manager support on SharedRingMemory itself.
    """

    def __init__(self, lock_path: str):
        self._lock_path = lock_path
        # Open once, kept open for the life of this object --- locking
        # an already-open fd is fast; opening a fresh fd per
        # acquire/release would reintroduce the same per-call
        # filesystem overhead that made the first fix slow.
        self._fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)
        # Probe once, here, rather than paying a seek on every acquire
        # and release for the rest of the process's life. See the
        # platform block above for why this is verified and not assumed.
        self._needs_seek = not _position_is_stable_after_locking(self._fd)

    def __enter__(self):
        _lock_fd(self._fd, self._needs_seek)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _unlock_fd(self._fd, self._needs_seek)
        return False

    def close(self):
        """Release the underlying fd. Idempotent, and safe to call
        even if the lock was never acquired."""
        fd, self._fd = self._fd, None
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass  # already closed, or the fd was never valid

    def __del__(self):
        # Safety net only --- callers should close() explicitly (or
        # use SharedRingMemory as a context manager). Interpreter
        # shutdown can already have torn down os.close, so guard it.
        try:
            self.close()
        except Exception:
            pass


class SharedRingMemory:
    """
    Manages a memory-mapped (mmap) region shared across processes.

    Layout: [ HEADER (16 bytes) ][ SLOT 0 ][ SLOT 1 ] ... [ SLOT N-1 ]
    Header stores: capacity, read_pointer, write_pointer, occupancy.

    Holds two OS resources (an mmap over the backing file and an fd on
    the lock file), so it must be closed. Use it as a context manager
    or call close() when done.
    """

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        create: bool = False,
        backing_file: str | None = None,
    ):
        """
        Open (or create) the shared memory region.

        Args:
            capacity: max number of order slots in the buffer.
            create: True to initialize a fresh region (first process
                    to start should use this); False to attach to an
                    already-existing region.
            backing_file: path to the mmap backing file. Defaults to
                    the module-level BACKING_FILE, which is what every
                    process uses in normal operation. Made a parameter
                    on Day 9 so tests and benchmarks can run against
                    isolated files instead of all sharing one global
                    path --- that global was why one failing test could
                    cascade into unrelated failures.
        """
        # Resolved at call time, not at import time, so that code which
        # monkeypatches shared.shared_memory.BACKING_FILE (see
        # benchmarks/serialization_comparison.py) still works.
        self.backing_file = backing_file if backing_file is not None else BACKING_FILE
        self.lock_file = lock_path_for(self.backing_file)

        self._closed = False
        self.mm = None
        self._file = None

        # Day 8 fix: was `self.lock = Lock()` (multiprocessing.Lock),
        # which does NOT synchronize across independently-started
        # processes --- each process attaching to this shared memory
        # got its own separate Lock, providing no real mutual
        # exclusion. See _CrossProcessLock's docstring above for the
        # full story (a real 1,000,000-order audit caught this as
        # silent data loss). Fixed with OS-native file locking, which
        # works correctly across any number of independently-started
        # processes since it's identified by a shared file path, not
        # a shared Python object.
        self.lock = _CrossProcessLock(self.lock_file)

        try:
            self.capacity = capacity
            self.total_size = HEADER_SIZE + (capacity * SLOT_SIZE)

            file_exists = os.path.exists(self.backing_file)
            initialize = create or not file_exists

            if initialize:
                self._ensure_backing_file(self.total_size)
            else:
                # Attaching: the creator's capacity is the source of
                # truth. Reading it from the header first means an
                # attaching process that guesses the capacity wrong
                # still maps the correct number of bytes, instead of
                # mapping a short region and then indexing past the
                # end of it.
                self.capacity = self._read_capacity_from_disk() or capacity
                self.total_size = HEADER_SIZE + (self.capacity * SLOT_SIZE)

            self._file = open(self.backing_file, "r+b")
            self.mm = mmap.mmap(self._file.fileno(), self.total_size)

            if initialize:
                self._write_header(
                    capacity=self.capacity, read_ptr=0, write_ptr=0, occupancy=0
                )
        except BaseException:
            # Never leave a half-built object holding an OS handle ---
            # that is precisely how the lock-file leak turned one
            # failure into a cascade of unrelated ones.
            self.close()
            raise

    def _ensure_backing_file(self, size: int):
        """Create the backing file at exactly `size` bytes, without
        truncating a file that may still be memory-mapped.

        Day 9 fix: this used to be an unconditional `open(path, "wb")`,
        which truncates. Windows refuses to truncate a file that has a
        live mapping and raises OSError [Errno 22] Invalid argument ---
        so a leaked mmap from an earlier test made the next test fail
        at construction time. Skipping the rewrite when the file is
        already the right size avoids the truncate entirely in the
        common case; the header is reset through the mmap afterwards,
        which is what actually makes the region "fresh".
        """
        if os.path.exists(self.backing_file) and os.path.getsize(self.backing_file) == size:
            return
        with open(self.backing_file, "wb") as f:
            f.write(b"\x00" * size)

    def _read_capacity_from_disk(self):
        """Peek at the header's capacity field before mapping, so the
        mapping can be sized correctly. Returns None if the file is
        too short or not yet initialized."""
        try:
            with open(self.backing_file, "rb") as f:
                raw = f.read(HEADER_SIZE)
        except OSError:
            return None
        if len(raw) < HEADER_SIZE:
            return None
        stored_capacity = struct.unpack(HEADER_FORMAT, raw)[0]
        return stored_capacity or None

    def _write_header(self, capacity, read_ptr, write_ptr, occupancy):
        """Internal: pack and write the 4-field header into the mmap."""
        struct.pack_into(HEADER_FORMAT, self.mm, 0,
                         capacity, read_ptr, write_ptr, occupancy)

    def read_header(self):
        """Return the current (capacity, read_ptr, write_ptr, occupancy).

        `unpack_from` reads straight out of the mapping. The previous
        `struct.unpack(HEADER_FORMAT, self.mm[0:HEADER_SIZE])` sliced
        the mmap first, which allocates a throwaway bytes object on
        every call --- and this is called on every single write and
        read, inside the lock.
        """
        return struct.unpack_from(HEADER_FORMAT, self.mm, 0)

    def update_header(self, read_ptr, write_ptr, occupancy, capacity=None):
        """Update the mutable header fields (capacity never changes).

        `capacity` is accepted so callers that have just read the header
        can pass it back in. Without it this method re-read the entire
        header purely to recover a field the caller already had ---
        doubling the header reads on the hot path, inside the lock, for
        a value that by definition cannot have changed.
        """
        if capacity is None:
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
        """Release the mmap, the backing file, and the lock fd.

        Idempotent, and each resource is released independently so one
        failure cannot strand the others.
        """
        if self._closed:
            return
        self._closed = True

        if self.mm is not None:
            try:
                self.mm.close()
            except (BufferError, ValueError):
                pass
            self.mm = None

        if self._file is not None:
            try:
                self._file.close()
            except OSError:
                pass
            self._file = None

        # Day 9 fix: this was the missing line. See _CrossProcessLock.
        if self.lock is not None:
            self.lock.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
