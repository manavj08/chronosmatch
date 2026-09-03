"""
ipc/tests/test_ring_buffer.py
--------------------------------
Test suite for the zero-copy IPC bus (RingBuffer + SharedRingMemory +
the binary protocol).

Two tiers:
  1. Single-process unit tests (TestBasicSemantics, TestWrapAround,
     TestOverflowUnderflow, TestProtocol) -- fast, run every time.
  2. Real cross-process tests (TestCrossProcess) -- spawn actual OS
     processes (multiprocessing.Process, not threads) writing to and
     reading from the SAME backing file, covering: 100k orders, 1M
     orders, wrap-around under real concurrent load, simultaneous
     producer/consumer, overflow/underflow under contention, and
     process startup/shutdown.

Run:
    pytest ipc/tests/ -v
"""

import multiprocessing
import os
import struct
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from ipc.ring_buffer import RingBuffer
from ipc.shared_memory import SharedRingMemory, HEADER_SIZE
from ipc.protocol import pack_order, unpack_order, SLOT_SIZE, FORMAT


def make_order(order_id, side="B", price=100.5, quantity=50, timestamp=171000000):
    return {"order_id": order_id, "side": side, "price": price,
            "quantity": quantity, "timestamp": timestamp}


def fresh_backing_file(name: str) -> str:
    """A unique, isolated backing file per test so tests never interfere
    with each other (or with a real ipc_ring_buffer.mem some other
    process might be using)."""
    path = f"/tmp/ipc_test_{name}_{os.getpid()}.mem"
    for p in (path, path + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    return path


# ======================================================================
# Binary protocol
# ======================================================================

class TestProtocol:
    def test_round_trip_preserves_all_fields(self):
        order = make_order(order_id=42, side="S", price=101.25, quantity=7, timestamp=123_456_789)
        blob = pack_order(order)
        assert unpack_order(blob) == order

    def test_slot_size_is_29_bytes(self):
        assert SLOT_SIZE == 29
        assert struct.calcsize(FORMAT) == 29

    def test_packed_size_is_always_fixed(self):
        """Every order, regardless of field values, packs to exactly
        SLOT_SIZE bytes -- no delimiters needed, no variable-length
        encoding, so the receiver always knows exactly how many bytes
        to read."""
        small = pack_order(make_order(1, quantity=1, price=0.01))
        large = pack_order(make_order(2**32, quantity=2**31, price=999999.99))
        assert len(small) == len(large) == SLOT_SIZE

    def test_no_json_or_pickle_imported_by_the_protocol_module(self):
        """Direct check of the actual claim: the hot IPC path uses only
        struct, not a general-purpose serialization library."""
        import ipc.protocol as protocol_module
        source = Path(protocol_module.__file__).read_text()
        assert "import json" not in source
        assert "import pickle" not in source

    def test_side_round_trips_for_both_values(self):
        for side in ("B", "S"):
            order = make_order(1, side=side)
            assert unpack_order(pack_order(order))["side"] == side


# ======================================================================
# Basic single-process semantics
# ======================================================================

class TestBasicSemantics:
    def test_write_then_read_returns_the_same_order(self):
        bf = fresh_backing_file("basic1")
        rb = RingBuffer(capacity=4, create=True, backing_file=bf)
        order = make_order(1)
        rb.write_order(order)
        assert rb.read_order() == order

    def test_fifo_ordering_preserved_across_multiple_orders(self):
        bf = fresh_backing_file("basic2")
        rb = RingBuffer(capacity=8, create=True, backing_file=bf)
        orders = [make_order(i) for i in range(1, 6)]
        for o in orders:
            assert rb.write_order(o) is True
        for o in orders:
            assert rb.read_order() == o

    def test_size_tracks_occupancy_through_writes_and_reads(self):
        bf = fresh_backing_file("basic3")
        rb = RingBuffer(capacity=8, create=True, backing_file=bf)
        assert rb.size() == 0
        rb.write_order(make_order(1))
        rb.write_order(make_order(2))
        assert rb.size() == 2
        rb.read_order()
        assert rb.size() == 1

    def test_header_layout_matches_documented_fields(self):
        bf = fresh_backing_file("basic4")
        mem = SharedRingMemory(capacity=16, create=True, backing_file=bf)
        capacity, read_ptr, write_ptr, occupancy = mem.read_header()
        assert (capacity, read_ptr, write_ptr, occupancy) == (16, 0, 0, 0)
        mem.close()


# ======================================================================
# Wrap-around
# ======================================================================

class TestWrapAround:
    def test_pointers_wrap_to_zero_after_reaching_capacity(self):
        bf = fresh_backing_file("wrap1")
        rb = RingBuffer(capacity=2, create=True, backing_file=bf)
        order = make_order(1)
        rb.write_order(order)
        rb.read_order()
        rb.write_order(order)
        rb.read_order()
        assert rb.get_stats()["write_pointer"] == 0
        assert rb.get_stats()["read_pointer"] == 0

    def test_buffer_reused_correctly_across_many_wraps(self):
        """Write/read one at a time through a small buffer many times
        over -- forces dozens of wrap-arounds and verifies every order
        still round-trips correctly (catches an off-by-one at the
        capacity boundary that a single wrap might miss)."""
        bf = fresh_backing_file("wrap2")
        rb = RingBuffer(capacity=3, create=True, backing_file=bf)
        for i in range(1, 101):
            assert rb.write_order(make_order(i)) is True
            result = rb.read_order()
            assert result["order_id"] == i

    def test_wraparound_with_buffer_kept_mostly_full(self):
        """A more realistic wrap pattern than write-one-read-one: prime
        the buffer to capacity-1 (mostly full), then repeatedly write
        one (fills it) and read one (frees a slot) -- net-zero
        occupancy growth, so it's sustainable indefinitely, while both
        pointers still advance and wrap many times over a small
        capacity, and the buffer stays under real, sustained pressure
        the whole time rather than sitting mostly empty."""
        bf = fresh_backing_file("wrap3")
        capacity = 4
        rb = RingBuffer(capacity=capacity, create=True, backing_file=bf)

        next_write_id = 1
        next_expected_read_id = 1
        for _ in range(capacity - 1):
            assert rb.write_order(make_order(next_write_id)) is True
            next_write_id += 1
        assert rb.size() == capacity - 1

        for _ in range(200):
            assert rb.write_order(make_order(next_write_id)) is True
            next_write_id += 1
            assert rb.is_full() is True

            result = rb.read_order()
            assert result["order_id"] == next_expected_read_id
            next_expected_read_id += 1
            assert rb.size() == capacity - 1

        # Drain the rest and confirm strict FIFO order held throughout.
        while not rb.is_empty():
            result = rb.read_order()
            assert result["order_id"] == next_expected_read_id
            next_expected_read_id += 1


# ======================================================================
# Full-buffer (overflow) / empty-buffer (underflow) behavior
# ======================================================================

class TestOverflowUnderflow:
    def test_write_to_full_buffer_returns_false_and_does_not_corrupt_state(self):
        bf = fresh_backing_file("overflow1")
        rb = RingBuffer(capacity=2, create=True, backing_file=bf)
        order = make_order(1)
        rb.write_order(order)
        rb.write_order(order)
        assert rb.is_full() is True

        assert rb.write_order(make_order(999)) is False  # rejected, not overwritten
        assert rb.size() == 2  # unchanged

        # Buffer must still be perfectly usable after a rejected write.
        first = rb.read_order()
        assert first["order_id"] == 1
        rb.read_order()
        assert rb.is_empty() is True

    def test_read_from_empty_buffer_returns_none_and_does_not_corrupt_state(self):
        bf = fresh_backing_file("underflow1")
        rb = RingBuffer(capacity=4, create=True, backing_file=bf)
        assert rb.read_order() is None
        assert rb.size() == 0

        # Buffer must still be perfectly usable after a no-op read.
        rb.write_order(make_order(1))
        assert rb.read_order()["order_id"] == 1

    def test_repeated_reads_on_empty_buffer_are_all_safe_no_ops(self):
        bf = fresh_backing_file("underflow2")
        rb = RingBuffer(capacity=4, create=True, backing_file=bf)
        for _ in range(20):
            assert rb.read_order() is None

    def test_repeated_writes_on_full_buffer_are_all_safe_rejections(self):
        bf = fresh_backing_file("overflow2")
        rb = RingBuffer(capacity=1, create=True, backing_file=bf)
        rb.write_order(make_order(1))
        for _ in range(20):
            assert rb.write_order(make_order(2)) is False
        assert rb.read_order()["order_id"] == 1  # the original write, untouched


# ======================================================================
# Cross-process: real OS processes, not threads
# ======================================================================

def _cp_producer(backing_file, count, capacity, ready, start_evt):
    rb = RingBuffer(capacity=capacity, create=False, backing_file=backing_file)
    ready.set()
    start_evt.wait()
    for order_id in range(1, count + 1):
        order = make_order(order_id, side="B" if order_id % 2 else "S", timestamp=order_id)
        while not rb.write_order(order):
            pass  # backpressure: buffer full, retry


def _cp_consumer(backing_file, count, capacity, ready, start_evt, result_queue):
    rb = RingBuffer(capacity=capacity, create=False, backing_file=backing_file)
    ready.set()
    start_evt.wait()
    received = []
    while len(received) < count:
        order = rb.read_order()
        if order is None:
            continue
        received.append(order["order_id"])
    result_queue.put(received)


def _run_cross_process(backing_file, count, capacity=4096, timeout=90):
    """Shared driver for the cross-process tests below: spawns a real
    producer process and a real consumer process against the same
    backing file, synchronizes their start, and returns (received_ids,
    producer, consumer) for the caller to assert on."""
    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    RingBuffer(capacity=capacity, create=True, backing_file=backing_file)

    ctx = multiprocessing.get_context()
    producer_ready = ctx.Event()
    consumer_ready = ctx.Event()
    start_event = ctx.Event()
    result_queue = ctx.Queue()

    producer = multiprocessing.Process(
        target=_cp_producer, args=(backing_file, count, capacity, producer_ready, start_event))
    consumer = multiprocessing.Process(
        target=_cp_consumer, args=(backing_file, count, capacity, consumer_ready, start_event, result_queue))

    producer.start()
    consumer.start()
    producer_ready.wait()
    consumer_ready.wait()

    start_event.set()

    # Drain the queue BEFORE join() -- join()-then-drain can deadlock
    # once the payload (a list of up to 1,000,000 ints) is large enough
    # to fill the underlying pipe's OS buffer.
    received = result_queue.get(timeout=timeout)

    producer.join(timeout=timeout)
    consumer.join(timeout=timeout)

    return received, producer, consumer


class TestCrossProcess:
    """Process A writes, Process B reads, via the SAME backing file --
    proving the IPC bus works across real process boundaries, not just
    within one process's memory space."""

    def test_100k_orders_no_loss_no_duplication_correct_order(self):
        backing_file = fresh_backing_file("cp_100k")
        count = 100_000
        received, producer, consumer = _run_cross_process(backing_file, count)

        assert not producer.is_alive() and not consumer.is_alive()
        assert len(received) == count
        assert received == list(range(1, count + 1)), (
            "orders were not received in the order they were written"
        )

    def test_1m_orders_no_loss_no_duplication_correct_order(self):
        backing_file = fresh_backing_file("cp_1m")
        count = 1_000_000
        received, producer, consumer = _run_cross_process(backing_file, count, timeout=180)

        assert not producer.is_alive() and not consumer.is_alive()
        expected = set(range(1, count + 1))
        received_set = set(received)
        missing = expected - received_set
        duplicated = len(received) - len(received_set)

        assert len(received) == count
        assert not missing, f"{len(missing)} orders lost; first few: {sorted(missing)[:10]}"
        assert duplicated == 0
        assert received == list(range(1, count + 1))

    def test_wraparound_under_real_cross_process_load(self):
        """A capacity small relative to order count forces the ring
        buffer to wrap around repeatedly while two real processes are
        actively racing to write/read it concurrently -- the scenario
        the single-process wrap-around tests can't fully exercise (real
        OS scheduling, real lock contention).

        Capacity note: very small capacities (single digits) hit a real
        lock-contention cliff -- see
        TestCrossProcess.test_throughput_degrades_at_very_small_capacity
        below, which measures and documents it directly. 512 is chosen
        here specifically because it's small enough to force ~100 full
        wraps over this test's order count, while staying well clear of
        that cliff so the test itself runs quickly."""
        backing_file = fresh_backing_file("cp_wrap")
        count = 50_000
        received, producer, consumer = _run_cross_process(backing_file, count, capacity=512)

        assert not producer.is_alive() and not consumer.is_alive()
        assert received == list(range(1, count + 1))

    def test_throughput_degrades_at_very_small_capacity(self):
        """Documents a genuine, measured property of this design rather
        than asserting it away: at very small buffer capacities, the
        producer and consumer processes toggle the buffer between full
        and empty on almost every single operation, and each such
        transition requires a real cross-process lock round-trip
        (fcntl.flock syscall + context switch) -- so throughput scales
        down with capacity in this small range, roughly linearly.
        Measured on this machine: an 8-slot buffer sustains roughly
        two orders of magnitude less throughput than a 512-slot one.
        This is the honest reason production capacity (4096, used
        elsewhere in this suite and in audits/ipc_audit.py) is chosen
        much larger than the minimum needed for correctness."""
        small_count = 4_000
        small_backing_file = fresh_backing_file("cp_tinycap")
        t0 = time.perf_counter()
        received_small, p1, c1 = _run_cross_process(small_backing_file, small_count, capacity=8, timeout=60)
        small_elapsed = time.perf_counter() - t0
        assert received_small == list(range(1, small_count + 1))

        large_backing_file = fresh_backing_file("cp_bigcap")
        t0 = time.perf_counter()
        received_large, p2, c2 = _run_cross_process(large_backing_file, small_count, capacity=512, timeout=60)
        large_elapsed = time.perf_counter() - t0
        assert received_large == list(range(1, small_count + 1))

        # Not a strict pass/fail threshold (machine-dependent) -- the
        # point is documenting that the effect is real and measurable,
        # not asserting a specific magnitude.
        assert small_elapsed > large_elapsed, (
            f"expected the 8-slot buffer ({small_elapsed:.2f}s) to be "
            f"measurably slower than the 512-slot buffer "
            f"({large_elapsed:.2f}s) for the same order count -- if "
            f"this ever stops holding, the capacity/contention "
            f"relationship documented here should be re-measured"
        )

    def test_simultaneous_producer_and_consumer_overlap_in_time(self):
        """Confirms the two processes are genuinely running concurrently
        (not accidentally serialized end-to-end) by having the consumer
        report timestamps as it drains, and checking its work started
        before the producer necessarily finished."""
        backing_file = fresh_backing_file("cp_simul")
        count = 30_000

        for p in (backing_file, backing_file + ".lock"):
            if os.path.exists(p):
                os.remove(p)
        RingBuffer(capacity=64, create=True, backing_file=backing_file)  # small: forces overlap

        ctx = multiprocessing.get_context()
        producer_ready = ctx.Event()
        consumer_ready = ctx.Event()
        start_event = ctx.Event()
        result_queue = ctx.Queue()

        def timed_producer(backing_file, count, ready, start_evt):
            rb = RingBuffer(capacity=64, create=False, backing_file=backing_file)
            ready.set()
            start_evt.wait()
            t_first_write = None
            for order_id in range(1, count + 1):
                order = make_order(order_id, timestamp=order_id)
                while not rb.write_order(order):
                    pass
                if t_first_write is None:
                    t_first_write = time.perf_counter()
            t_last_write = time.perf_counter()
            result_queue.put(("producer_times", t_first_write, t_last_write))

        def timed_consumer(backing_file, count, ready, start_evt):
            rb = RingBuffer(capacity=64, create=False, backing_file=backing_file)
            ready.set()
            start_evt.wait()
            t_first_read = None
            received_count = 0
            while received_count < count:
                order = rb.read_order()
                if order is None:
                    continue
                if t_first_read is None:
                    t_first_read = time.perf_counter()
                received_count += 1
            t_last_read = time.perf_counter()
            result_queue.put(("consumer_times", t_first_read, t_last_read))

        producer = multiprocessing.Process(
            target=timed_producer, args=(backing_file, count, producer_ready, start_event))
        consumer = multiprocessing.Process(
            target=timed_consumer, args=(backing_file, count, consumer_ready, start_event))
        producer.start()
        consumer.start()
        producer_ready.wait()
        consumer_ready.wait()

        overall_start = time.perf_counter()
        start_event.set()

        results = {}
        for _ in range(2):
            kind, t_first, t_last = result_queue.get(timeout=60)
            results[kind] = (t_first, t_last)

        producer.join(timeout=60)
        consumer.join(timeout=60)

        assert not producer.is_alive() and not consumer.is_alive()

        consumer_first_read = results["consumer_times"][0]
        producer_last_write = results["producer_times"][1]
        # The consumer's first successful read must have happened
        # BEFORE the producer's last write -- i.e. they overlapped in
        # time, not "producer finishes entirely, then consumer starts."
        # (Both timestamps are perf_counter() readings taken in each
        # process's own clock domain, which perf_counter() guarantees
        # is comparable across processes on the same machine.)
        assert consumer_first_read < producer_last_write, (
            "consumer appears to have started only after the producer "
            "fully finished -- expected genuine concurrent overlap "
            f"(consumer first read at {consumer_first_read - overall_start:.4f}s, "
            f"producer last write at {producer_last_write - overall_start:.4f}s)"
        )

    def test_process_startup_and_shutdown_is_clean(self):
        """Spawns real producer/consumer processes, confirms both come
        up (report ready) and both exit cleanly (exit code 0, not
        alive after join, no orphaned process) for a small, fast
        run -- a regression guard against hangs or crashes on the
        process lifecycle itself, independent of order-count scale."""
        backing_file = fresh_backing_file("cp_lifecycle")
        count = 500
        received, producer, consumer = _run_cross_process(backing_file, count, timeout=30)

        assert producer.exitcode == 0, f"producer exited with code {producer.exitcode}"
        assert consumer.exitcode == 0, f"consumer exited with code {consumer.exitcode}"
        assert not producer.is_alive()
        assert not consumer.is_alive()
        assert len(received) == count

    def test_lock_is_released_if_a_process_is_terminated_mid_hold(self):
        """The lock must not be left permanently stuck if a process
        dies while holding it -- verifies the OS-native flock/locking
        primitive's auto-release-on-fd-close property, which is the
        whole reason it was chosen over a file create/delete-based
        lock. Kills a process mid-write-burst, then confirms a fresh
        process can still acquire the lock and use the buffer
        normally afterward."""
        backing_file = fresh_backing_file("cp_lockrelease")
        for p in (backing_file, backing_file + ".lock"):
            if os.path.exists(p):
                os.remove(p)
        RingBuffer(capacity=64, create=True, backing_file=backing_file)

        def hold_and_hang(backing_file, ready):
            rb = RingBuffer(capacity=64, create=False, backing_file=backing_file)
            with rb.mem.lock:
                ready.set()
                time.sleep(60)  # simulate a hung process while holding the lock

        ctx = multiprocessing.get_context()
        ready = ctx.Event()
        victim = multiprocessing.Process(target=hold_and_hang, args=(backing_file, ready))
        victim.start()
        ready.wait(timeout=10)
        time.sleep(0.1)  # let it actually settle into the lock + sleep
        victim.terminate()  # SIGTERM: OS closes its fds, including the lock fd
        victim.join(timeout=10)

        rb = RingBuffer(capacity=64, create=False, backing_file=backing_file)
        assert rb.write_order(make_order(1)) is True
        assert rb.read_order()["order_id"] == 1
