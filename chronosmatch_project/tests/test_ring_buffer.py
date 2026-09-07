"""
tests/test_ring_buffer.py
----------------------------
Core single-process behaviour of the ring buffer: write/read round
trips, empty and full detection, and pointer wraparound.

Every test takes the `ring_buffer` fixture (see conftest.py) rather
than constructing RingBuffer directly. That gives each test its own
backing file and guarantees the buffer's OS handles are released when
the test ends --- previously these tests shared one global file and
never closed anything, which leaked a lock-file handle per test and
broke later tests on Windows.
"""


def make_order(order_id=1, side="B", price=100.5, quantity=50, timestamp=171000000):
    return {
        "order_id": order_id,
        "side": side,
        "price": price,
        "quantity": quantity,
        "timestamp": timestamp,
    }


def test_write_and_read(ring_buffer):
    rb = ring_buffer(capacity=4)
    order = make_order()
    rb.write_order(order)
    result = rb.read_order()
    assert result == order


def test_empty_buffer_is_empty(ring_buffer):
    rb = ring_buffer(capacity=4)
    assert rb.is_empty() is True


def test_full_buffer(ring_buffer):
    rb = ring_buffer(capacity=2)
    order = make_order()
    rb.write_order(order)
    rb.write_order(order)
    assert rb.is_full() is True
    assert rb.write_order(order) is False


def test_wraparound(ring_buffer):
    rb = ring_buffer(capacity=2)
    order = make_order()
    rb.write_order(order)
    rb.read_order()
    rb.write_order(order)
    rb.read_order()
    assert rb.get_stats()["write_pointer"] == 0
    assert rb.get_stats()["read_pointer"] == 0


def test_multiple_writes(ring_buffer):
    rb = ring_buffer(capacity=4)
    orders = [
        make_order(1, "B", 100.0, 10, 1),
        make_order(2, "S", 101.0, 20, 2),
        make_order(3, "B", 102.0, 30, 3),
    ]
    for o in orders:
        assert rb.write_order(o) is True

    assert rb.size() == 3

    for o in orders:
        assert rb.read_order() == o

    assert rb.is_empty() is True


def test_close_is_idempotent(ring_buffer):
    """Day 9 regression guard: close() releases the mmap and the lock
    file descriptor, and calling it twice must not raise. Without a
    working close() the lock file stays open forever, which on Windows
    makes it undeletable."""
    rb = ring_buffer(capacity=4)
    rb.close()
    rb.close()


def test_context_manager_closes_buffer(ring_buffer):
    """A RingBuffer used as a context manager is closed on exit, so its
    backing file can be replaced or deleted afterwards."""
    rb = ring_buffer(capacity=4)
    with rb:
        rb.write_order(make_order())
    assert rb.mem.mm is None, "mapping should be released on context exit"


def test_attaching_process_adopts_creator_capacity(ring_buffer):
    """An attaching handle that guesses the capacity wrong must still
    map the region the creator actually made, rather than mapping a
    short region and indexing past the end of it."""
    creator = ring_buffer(capacity=64, create=True)
    attached = ring_buffer(capacity=8, create=False)

    assert attached.get_stats()["capacity"] == 64
    assert attached.mem.capacity == 64

    creator.write_order(make_order(order_id=7))
    assert attached.read_order()["order_id"] == 7


def test_recreating_region_does_not_truncate_a_mapped_file(ring_buffer):
    """Day 9 regression guard for the OSError [Errno 22] failure.

    Creating a region used to do an unconditional open(path, "wb"),
    which truncates. Windows refuses to truncate a file that has a live
    memory mapping, so if any other handle was still mapped --- for
    instance one held alive by a previous test's traceback --- the next
    create failed at construction with "Invalid argument". Re-creating
    at the same capacity must now reset the header through the mapping
    instead of rewriting the file.
    """
    first = ring_buffer(capacity=32, create=True)
    first.write_order(make_order(order_id=99))
    assert first.size() == 1

    # A second creator while `first` is still mapped. This is the call
    # that used to raise on Windows.
    second = ring_buffer(capacity=32, create=True)

    assert second.size() == 0, "create=True should reset the region"
    assert first.size() == 0, "both handles view the same region"

    second.write_order(make_order(order_id=100))
    assert first.read_order()["order_id"] == 100
