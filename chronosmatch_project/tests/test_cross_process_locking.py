"""
tests/test_cross_process_locking.py
--------------------------------------
Day 8: regression test for a real, serious bug found while building
the Mid-Project Review IPC audit (see audits/ipc_audit.py and
CHANGELOG.md's Day 8 entry for the full story).

The bug: shared/shared_memory.py's SharedRingMemory used to do
`self.lock = Lock()` (multiprocessing.Lock). That only synchronizes
processes that share the SAME Lock object --- it does NOT work when
multiple independently-started processes each construct their own
RingBuffer() by opening the same backing file path, which is exactly
how every process in this project attaches to shared memory. Each
process silently got its own separate, non-cooperating lock. Under
concurrent load this caused real data loss: in one 20,000-order
manual test, ~31% of orders vanished with no error or crash.

This test reproduces the scenario directly (two real OS processes,
one writing, one reading, verifying completeness) at a much smaller
scale than the full 1,000,000-order audit script, so it runs fast
enough for routine `pytest` runs while still being large enough to
reliably trigger the race if the locking regressed to the old
per-process-Lock() behavior. The full-scale audit
(audits/ipc_audit.py) remains the authoritative large-scale proof;
this test exists so a future accidental regression gets caught
immediately by `pytest`, not only by someone remembering to run the
manual audit script.
"""

import multiprocessing
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.ring_buffer import RingBuffer

TEST_ORDER_COUNT = 20_000  # enough to reliably reproduce the old race;
                            # small enough to run in well under a minute


# Day 9: the backing-file path is now passed in as an argument rather
# than every process implicitly using one module-global path. The
# children still attach by path, exactly as a real deployment would ---
# they just get told which path. This lets each test run against its
# own isolated file, so one test can never inherit a half-written
# region from another, and cleanup cannot collide with a file another
# test is still holding open.
#
# Both children also close their buffers before exiting. Each open
# RingBuffer holds an fd on the lock file, and on Windows an open
# handle makes that file undeletable (WinError 32) --- which is what
# made these tests fail even though the IPC logic itself was correct.


def _producer(ready, start_evt, count, backing_file):
    with RingBuffer(capacity=1024, create=False, backing_file=backing_file) as rb:
        ready.set()
        start_evt.wait()
        for order_id in range(1, count + 1):
            order = {
                "order_id": order_id, "side": "B", "price": 100.0,
                "quantity": 1, "timestamp": order_id,
            }
            while not rb.write_order(order):
                pass


def _consumer(ready, start_evt, count, result_queue, backing_file):
    with RingBuffer(capacity=1024, create=False, backing_file=backing_file) as rb:
        ready.set()
        start_evt.wait()
        received = []
        while len(received) < count:
            order = rb.read_order()
            if order is None:
                continue
            received.append(order["order_id"])
        result_queue.put(received)


def test_no_data_loss_between_two_real_processes(shared_ipc_path):
    """The core regression check: every order written by a real,
    separate producer process must be received exactly once by a
    real, separate consumer process, with no loss and no duplication.
    This is exactly the property the old per-process Lock() bug
    violated."""
    # The `shared_ipc_path` fixture (conftest.py) supplies a fresh,
    # per-test path and removes both files afterwards, replacing the
    # manual delete-the-global-file dance that used to live here.
    backing_file = shared_ipc_path

    with RingBuffer(capacity=1024, create=True, backing_file=backing_file):
        pass  # create and initialize the region, then release the handle

    ctx = multiprocessing.get_context()
    producer_ready = ctx.Event()
    consumer_ready = ctx.Event()
    start_event = ctx.Event()
    result_queue = ctx.Queue()

    producer = multiprocessing.Process(
        target=_producer,
        args=(producer_ready, start_event, TEST_ORDER_COUNT, backing_file))
    consumer = multiprocessing.Process(
        target=_consumer,
        args=(consumer_ready, start_event, TEST_ORDER_COUNT, result_queue, backing_file))

    producer.start()
    consumer.start()
    producer_ready.wait()
    consumer_ready.wait()

    start_event.set()

    # Drain the queue BEFORE join() --- see audits/ipc_audit.py's Day 8
    # comment for why: join()-then-drain can deadlock when the child
    # writes a large payload through the queue's pipe.
    received = result_queue.get(timeout=60)

    producer.join(timeout=30)
    consumer.join(timeout=30)

    assert not producer.is_alive(), "producer process failed to exit cleanly"
    assert not consumer.is_alive(), "consumer process failed to exit cleanly"

    expected_ids = set(range(1, TEST_ORDER_COUNT + 1))
    received_id_set = set(received)

    missing = expected_ids - received_id_set
    duplicated_count = len(received) - len(received_id_set)

    assert len(received) == TEST_ORDER_COUNT, (
        f"Expected {TEST_ORDER_COUNT} orders, consumer reported "
        f"{len(received)} --- possible hang or early exit"
    )
    assert not missing, (
        f"{len(missing)} orders were lost in transit between two real "
        f"processes --- this is exactly the cross-process locking bug "
        f"found on Day 8. First few missing ids: {sorted(missing)[:10]}"
    )
    assert duplicated_count == 0, (
        f"{duplicated_count} orders were delivered more than once"
    )
    assert received == list(range(1, TEST_ORDER_COUNT + 1)), (
        "Orders were not received in the order they were written --- "
        "violates the single-producer/single-consumer FIFO guarantee"
    )
