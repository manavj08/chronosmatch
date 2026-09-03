"""
audits/ipc_audit.py
----------------------
Day 8: MID-PROJECT REVIEW --- "Prove the zero-copy architecture works
by sending 1M orders between two Python processes without hitting the
CPU bottleneck of Pickling."

This is a correctness-and-throughput audit, not just a throughput
benchmark (benchmarks/throughput_benchmark.py already covers raw
speed). The claims this script actually verifies:

1. ZERO-COPY / NO SERIALIZATION LIBRARY: confirmed by code inspection,
   not by this script --- shared/serializer.py uses Python's struct
   module (raw byte packing) and shared/shared_memory.py uses mmap.
   Neither json nor pickle is imported anywhere in the shared/
   package. This script's job is proving the RESULT of that design
   holds under real load, not re-deriving the design claim itself.

2. TWO REAL OS PROCESSES: uses multiprocessing.Process (as every
   other demo in this project does), not threading --- confirmed by
   printing each process's real OS pid.

3. COMPLETENESS: every one of 1,000,000 orders written is read back
   exactly once. No orders lost, none duplicated. Verified by
   tracking the full set of order_ids received (not just a count) ---
   a count alone could hide a scenario where some orders were
   silently dropped and others silently duplicated to the same total.

4. ORDERING: since this is a single-producer/single-consumer ring
   buffer, orders must arrive in the exact sequence they were
   written. Verified directly, not assumed.

5. THROUGHPUT UNDER SUSTAINED LOAD: reports orders/sec for the full
   1,000,000-order run, uncapped (no artificial rate limiting) ---
   this is the real "CPU bottleneck" test the spec asks for: if
   Pickle/JSON serialization were happening, this number would be
   dramatically lower than what the earlier Day 4 asyncio benchmark
   already showed for the same struct-based approach.

Honesty note (same as benchmarks/throughput_benchmark.py): the
throughput number reported here is whatever THIS machine achieves,
not a production hardware claim.

Run:
    python setup_demo.py         (one-time, if not already built)
    python audits/ipc_audit.py
"""

import multiprocessing
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from shared.ring_buffer import RingBuffer

TOTAL_ORDERS = int(os.environ.get("IPC_AUDIT_ORDERS", 1_000_000))
RING_BUFFER_CAPACITY = 4096
PROGRESS_INTERVAL = max(1, TOTAL_ORDERS // 20)  # ~20 progress lines regardless of scale


def producer_process(ready_event, start_event, result_queue):
    """Real, separate OS process. Writes TOTAL_ORDERS sequentially
    numbered orders into the shared-memory ring buffer as fast as
    possible --- no artificial rate limiting, no sleeps between
    writes (only backpressure waiting for the consumer when the
    buffer is genuinely full)."""
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    ready_event.set()
    start_event.wait()  # synchronize both processes to start together

    start_time = time.perf_counter()
    for order_id in range(1, TOTAL_ORDERS + 1):
        order = {
            "order_id": order_id,
            "side": "B" if order_id % 2 == 0 else "S",
            "price": 100.0 + (order_id % 500) * 0.01,
            "quantity": (order_id % 100) + 1,
            "timestamp": order_id,  # not perf_counter_ns() on purpose:
                                     # deterministic, lets the consumer
                                     # verify ordering trivially
        }
        while not rb.write_order(order):
            pass  # spin briefly on backpressure; buffer will drain

    elapsed = time.perf_counter() - start_time
    result_queue.put(("producer", elapsed, os.getpid()))


def consumer_process(ready_event, start_event, result_queue):
    """Real, separate OS process. Reads from the SAME shared memory
    region and verifies completeness + ordering directly, not just
    counting."""
    rb = RingBuffer(capacity=RING_BUFFER_CAPACITY, create=False)
    ready_event.set()
    start_event.wait()

    received_ids = []
    start_time = time.perf_counter()

    while len(received_ids) < TOTAL_ORDERS:
        order = rb.read_order()
        if order is None:
            continue
        received_ids.append(order["order_id"])
        if len(received_ids) % PROGRESS_INTERVAL == 0:
            elapsed_so_far = time.perf_counter() - start_time
            rate = len(received_ids) / elapsed_so_far if elapsed_so_far > 0 else 0
            print(f"  ... {len(received_ids):,}/{TOTAL_ORDERS:,} received "
                  f"({rate:,.0f}/sec so far)", flush=True)

    elapsed = time.perf_counter() - start_time
    result_queue.put(("consumer", elapsed, os.getpid(), received_ids))


def main():
    backing_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ring_buffer.mem")
    if os.path.exists(backing_file):
        os.remove(backing_file)

    RingBuffer(capacity=RING_BUFFER_CAPACITY, create=True)

    print("=" * 70)
    print("ChronosMatch — Mid-Project Review: IPC Audit (Day 8)")
    print(f"Sending {TOTAL_ORDERS:,} orders between two real OS processes")
    print("via zero-copy shared memory (no sockets, no Pickle, no JSON).")
    print("=" * 70)

    ctx = multiprocessing.get_context()
    producer_ready = ctx.Event()
    consumer_ready = ctx.Event()
    start_event = ctx.Event()
    result_queue = ctx.Queue()

    producer = multiprocessing.Process(
        target=producer_process, args=(producer_ready, start_event, result_queue), name="producer")
    consumer = multiprocessing.Process(
        target=consumer_process, args=(consumer_ready, start_event, result_queue), name="consumer")

    producer.start()
    consumer.start()

    # Wait for both processes to be alive and past setup before
    # signaling them to start, so the timed portion is pure
    # write/read work, not process-spawn overhead.
    producer_ready.wait()
    consumer_ready.wait()

    print(f"\nProducer pid={producer.pid}, Consumer pid={consumer.pid}")
    print("Both processes ready. Starting timed run...\n")

    overall_start = time.perf_counter()
    start_event.set()

    # Day 8 fix: read from result_queue BEFORE calling join(), not
    # after. This was a real hang found while running this exact
    # script: join()-then-drain is a well-known multiprocessing
    # deadlock hazard when a child puts a large payload on the queue
    # (here, a list of up to 1,000,000 order ids) --- the queue is
    # backed by a pipe with a background feeder thread; if the pipe's
    # OS buffer fills before the parent reads it, the child blocks
    # trying to write, and the parent's join() blocks waiting for the
    # child to exit, and neither side can proceed. Draining the queue
    # first (get() blocks until an item is available, which is fine
    # here since we know exactly how many items to expect) avoids the
    # deadlock entirely.
    results = {}
    received_ids = None
    for _ in range(2):
        item = result_queue.get()
        if item[0] == "producer":
            results["producer"] = item
        else:
            results["consumer"] = item
            received_ids = item[3]

    producer.join()
    consumer.join()
    overall_elapsed = time.perf_counter() - overall_start

    producer_elapsed = results["producer"][1]
    consumer_elapsed = results["consumer"][1]
    consumer_pid = results["consumer"][2]
    producer_pid = results["producer"][2]

    # --- Verification: completeness ---
    expected_ids = set(range(1, TOTAL_ORDERS + 1))
    received_id_set = set(received_ids)
    missing = expected_ids - received_id_set
    duplicated = len(received_ids) - len(received_id_set)

    # --- Verification: ordering ---
    is_ordered = received_ids == list(range(1, TOTAL_ORDERS + 1))

    print("=" * 70)
    print("RESULTS")
    print("=" * 70)
    print(f"Two real OS processes confirmed: producer pid={producer_pid}, "
          f"consumer pid={consumer_pid} (different pids = real processes, "
          f"not threads)")
    print(f"Orders sent:      {TOTAL_ORDERS:,}")
    print(f"Orders received:  {len(received_ids):,}")
    print(f"Missing orders:   {len(missing)} {'(NONE — all accounted for)' if not missing else missing}")
    print(f"Duplicated:       {duplicated}")
    print(f"Correct ordering: {is_ordered}")
    print()
    print(f"Producer wall time: {producer_elapsed:.3f}s "
          f"({TOTAL_ORDERS / producer_elapsed:,.0f} orders/sec written)")
    print(f"Consumer wall time: {consumer_elapsed:.3f}s "
          f"({TOTAL_ORDERS / consumer_elapsed:,.0f} orders/sec read)")
    print(f"Overall wall time:  {overall_elapsed:.3f}s "
          f"({TOTAL_ORDERS / overall_elapsed:,.0f} orders/sec end-to-end)")
    print("=" * 70)

    success = (not missing) and (duplicated == 0) and is_ordered
    if success:
        print("AUDIT PASSED: all orders delivered exactly once, in order, "
              "via zero-copy shared memory between two real processes.")
    else:
        print("AUDIT FAILED: see discrepancies above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
