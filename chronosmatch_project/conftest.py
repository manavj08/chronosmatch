"""
conftest.py
--------------
Shared pytest fixtures for the whole suite.

Day 9. Before this file existed, every test that needed a RingBuffer
built one directly against the single module-global backing-file path
in shared/shared_memory.py, and none of them closed it. Two
consequences, both of which only showed up on Windows:

1. Each RingBuffer holds an open handle on the lock file. Leaking them
   meant a later test could not delete that file --- WinError 32,
   "the process cannot access the file because it is being used by
   another process". POSIX allows unlinking a file that still has open
   handles, so the leak was invisible on Linux and macOS.

2. Because every test shared ONE backing file, a single failing test
   could poison the ones after it. pytest keeps a failed test's
   traceback for its report, the traceback keeps that test's frame
   alive, and the frame keeps its RingBuffer --- and therefore its
   memory mapping --- alive for the rest of the session. The next test
   to call open(path, "wb") then hit OSError [Errno 22], because
   Windows will not truncate a file that has a live mapping.

The `ring_buffer` fixture below fixes both at the source: each test
gets its own backing file under pytest's tmp_path, and every buffer it
hands out is closed when the test ends, pass or fail.
"""

import gc
import os

import pytest

from shared.ring_buffer import RingBuffer
from shared.shared_memory import BACKING_FILE, lock_path_for


@pytest.fixture
def ring_buffer(tmp_path):
    """Factory for RingBuffers that are isolated per test and always
    closed afterwards.

    Usage:
        def test_something(ring_buffer):
            rb = ring_buffer(capacity=8)
            ...

    Every buffer from one call to this fixture shares the same backing
    file, so a test can build a second attached handle to the same
    region (`ring_buffer(capacity=8, create=False)`) when it needs to
    exercise the attach path.
    """
    backing_file = str(tmp_path / "ring_buffer.mem")
    created = []

    def _make(capacity=1024, create=True, **kwargs):
        rb = RingBuffer(
            capacity=capacity, create=create, backing_file=backing_file, **kwargs
        )
        created.append(rb)
        return rb

    _make.backing_file = backing_file
    _make.lock_file = lock_path_for(backing_file)

    yield _make

    for rb in created:
        rb.close()


@pytest.fixture
def shared_ipc_path(tmp_path):
    """A backing-file path for tests that spawn real child processes.

    Cross-process tests cannot use an in-process fixture object; they
    need a path string they can pass to the children as an argument.
    This gives them one that is unique per test, so concurrent or
    repeated runs never collide, and cleans up both files afterwards.
    """
    backing_file = str(tmp_path / "ring_buffer.mem")

    yield backing_file

    gc.collect()  # release any handle held by a buffer going out of scope
    for path in (backing_file, lock_path_for(backing_file)):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            # Best effort. tmp_path is disposable, so a file we cannot
            # remove here is not worth failing an otherwise-green test.
            pass


@pytest.fixture(autouse=True)
def _release_leaked_handles():
    """Safety net for any buffer built outside the fixtures above.

    RingBuffer and SharedRingMemory both close themselves on __del__,
    so forcing a collection between tests turns a leaked handle into a
    released one. This is a backstop, not a substitute for closing
    buffers explicitly --- it cannot help when pytest is still holding
    a failed test's frame alive.
    """
    yield
    gc.collect()


@pytest.fixture(scope="session", autouse=True)
def _clean_default_backing_files():
    """Remove any stale default-path IPC files left behind by a demo
    script or an interrupted earlier run, before and after the session.

    Tests use isolated paths, but `python run_demo.py` and friends use
    the default one, and a leftover file there with a mismatched
    capacity would be picked up by anything that attaches instead of
    creates.
    """

    def _sweep():
        gc.collect()
        for path in (BACKING_FILE, lock_path_for(BACKING_FILE)):
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError:
                pass

    _sweep()
    yield
    _sweep()
