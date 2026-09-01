"""
tests/test_cross_process_scenarios.py
-----------------------------------------
Closes two gaps found doing a full pass of the cross-process IPC
testing requirement list against what already existed:

1. A dedicated 100,000-order cross-process scenario. The existing
   tests/test_cross_process_locking.py test runs at 20,000 orders --
   enough to reliably reproduce the specific historical locking bug it
   guards against, but the requirement list separately calls out
   100,000 orders as its own scenario. 100k is still fast enough (well
   under a minute here) to run as a normal pytest test directly, unlike
   the 1,000,000-order scale, which stays in audits/ipc_audit.py on
   purpose -- see that script's module docstring: it's the authoritative
   large-scale proof, deliberately kept out of the routine pytest suite
   so the test suite itself stays fast. This file follows that same
   established convention rather than re-litigating it.

2. Explicit process startup/shutdown verification: both processes'
   exit codes are asserted to be exactly 0 (not just "did we get all
   the data back"), which is a distinct claim -- a process could
   deliver all data and still crash on the way out (e.g. an unhandled
   exception in cleanup code), and that would slip past a test that
   only checks the received data.
"""

import multiprocessing
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.ring_buffer import RingBuffer


def _producer(ready, start_evt, count):
    rb = RingBuffer(capacity=4096, create=False)
    ready.set()
    start_evt.wait()
    for order_id in range(1, count + 1):
        order = {
            "order_id": order_id, "side": "B" if order_id % 2 else "S",
            "price": 100.0 + (order_id % 200) * 0.01,
            "quantity": (order_id % 50) + 1, "timestamp": order_id,
        }
        while not rb.write_order(order):
            pass


def _consumer(ready, start_evt, count, result_queue):
    rb = RingBuffer(capacity=4096, create=False)
    ready.set()
    start_evt.wait()
    received = []
    while len(received) < count:
        order = rb.read_order()
        if order is None:
            continue
        received.append(order["order_id"])
    result_queue.put(received)


def _fresh_backing_files():
    backing_file = str(Path(__file__).resolve().parent.parent / "ring_buffer.mem")
    lock_file = backing_file + ".lock"
    for path in (backing_file, lock_file):
        if os.path.exists(path):
            os.remove(path)


def _run(count, timeout=60):
    _fresh_backing_files()
    RingBuffer(capacity=4096, create=True)

    ctx = multiprocessing.get_context()
    producer_ready = ctx.Event()
    consumer_ready = ctx.Event()
    start_event = ctx.Event()
    result_queue = ctx.Queue()

    producer = multiprocessing.Process(
        target=_producer, args=(producer_ready, start_event, count))
    consumer = multiprocessing.Process(
        target=_consumer, args=(consumer_ready, start_event, count, result_queue))

    producer.start()
    consumer.start()
    producer_ready.wait()
    consumer_ready.wait()

    start_event.set()

    # Drain before join() -- see tests/test_cross_process_locking.py's
    # comment for why (join()-then-drain can deadlock on a large payload).
    received = result_queue.get(timeout=timeout)

    producer.join(timeout=timeout)
    consumer.join(timeout=timeout)

    return received, producer, consumer


def test_100k_orders_no_loss_no_duplication_correct_order():
    """The 100,000-order cross-process scenario, as its own dedicated
    test rather than folded into the 20,000-order locking-regression
    test above it in tests/test_cross_process_locking.py."""
    count = 100_000
    received, producer, consumer = _run(count)

    assert not producer.is_alive()
    assert not consumer.is_alive()

    expected_ids = set(range(1, count + 1))
    received_id_set = set(received)
    missing = expected_ids - received_id_set
    duplicated_count = len(received) - len(received_id_set)

    assert len(received) == count, (
        f"Expected {count} orders, consumer reported {len(received)}"
    )
    assert not missing, f"{len(missing)} orders lost; first few: {sorted(missing)[:10]}"
    assert duplicated_count == 0, f"{duplicated_count} orders delivered more than once"
    assert received == list(range(1, count + 1)), (
        "orders were not received in the order they were written"
    )


def test_process_startup_and_shutdown_is_clean():
    """Explicit process-lifecycle check: both the producer and consumer
    must not just deliver correct data, but also exit with code 0 --
    a clean shutdown, not a crash-after-finishing-work. Kept at a small
    scale since this test is about the lifecycle, not throughput."""
    count = 2_000
    received, producer, consumer = _run(count, timeout=30)

    assert producer.exitcode == 0, f"producer exited with code {producer.exitcode}"
    assert consumer.exitcode == 0, f"consumer exited with code {consumer.exitcode}"
    assert not producer.is_alive()
    assert not consumer.is_alive()
    assert len(received) == count


def test_repeated_startup_and_shutdown_cycles_stay_clean():
    """Runs several independent start-to-shutdown cycles back to back
    (fresh processes and a fresh backing file each time) -- guards
    against state leaking between runs, e.g. a stale lock file or a
    leftover mmap region from a previous cycle corrupting the next
    one's startup."""
    for cycle in range(3):
        count = 1_000
        received, producer, consumer = _run(count, timeout=20)

        assert producer.exitcode == 0, f"cycle {cycle}: producer exit code {producer.exitcode}"
        assert consumer.exitcode == 0, f"cycle {cycle}: consumer exit code {consumer.exitcode}"
        assert received == list(range(1, count + 1)), f"cycle {cycle}: data mismatch"
