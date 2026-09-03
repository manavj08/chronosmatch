"""
ipc/serialization_comparison.py
----------------------------------
"Can we move huge volumes of orders between processes without
serialization becoming the bottleneck?" -- this script measures it
directly rather than asserting it.

Produces a comparison table:

    Method                              Throughput      Serialization
    JSON (dumps + loads)                X ops/sec       Yes
    Pickle (dumps + loads)              X ops/sec       Yes
    struct (pack + unpack, this proj.)  X ops/sec       No
    mmap + struct (full RingBuffer      X ops/sec       No
      write_order + read_order)

Two things are measured, kept clearly separate:

1. PURE serialization cost: json.dumps/loads, pickle.dumps/loads, and
   struct.pack/unpack (via ipc.protocol) all operating on the exact
   same order dict, round-tripped, with no IPC transport involved at
   all -- isolates the serialization METHOD's own cost.

2. FULL IPC round trip for the struct method specifically: real
   RingBuffer.write_order() + read_order() calls, which include lock
   acquisition, header read/write, and the slot write/read -- the
   complete cost this project's IPC bus actually pays per order, not
   just the serialization step in isolation. JSON/Pickle don't get an
   equivalent row here because this project's ring buffer only speaks
   the fixed-size struct protocol (see protocol.py's module docstring
   for why fixed-size slots specifically enable that design); building
   a second, variable-length-framed mmap transport just to benchmark
   JSON/Pickle over it is out of scope, but the pure serialization
   numbers already show why fixed-size struct packing was chosen: JSON
   and Pickle both need variable-length framing (a length prefix or a
   delimiter) precisely because their output size varies per message,
   which the struct protocol avoids entirely by being fixed-size.

Run:
    python ipc/serialization_comparison.py [n]
"""

import json
import os
import pickle
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ipc.protocol import pack_order, unpack_order
from ipc.ring_buffer import RingBuffer

DEFAULT_N = 500_000

SAMPLE_ORDER = {
    "order_id": 123456,
    "side": "B",
    "price": 101.25,
    "quantity": 250,
    "timestamp": 123_456_789_012,
}


def bench_json(n: int) -> float:
    order = SAMPLE_ORDER
    t0 = time.perf_counter()
    for _ in range(n):
        blob = json.dumps(order)
        _ = json.loads(blob)
    elapsed = time.perf_counter() - t0
    return n / elapsed


def bench_pickle(n: int) -> float:
    order = SAMPLE_ORDER
    t0 = time.perf_counter()
    for _ in range(n):
        blob = pickle.dumps(order)
        _ = pickle.loads(blob)
    elapsed = time.perf_counter() - t0
    return n / elapsed


def bench_struct(n: int) -> float:
    order = SAMPLE_ORDER
    t0 = time.perf_counter()
    for _ in range(n):
        blob = pack_order(order)
        _ = unpack_order(blob)
    elapsed = time.perf_counter() - t0
    return n / elapsed


def bench_full_ring_buffer(n: int) -> float:
    """Full IPC round trip: real write_order()/read_order() calls
    (lock + header + slot), not just the serialization step -- what
    this project's IPC bus actually costs per order, single-process
    (no cross-process contention here; see ipc/tests/test_ring_buffer.py
    and audits/ipc_audit.py for real two-process throughput numbers)."""
    backing_file = "/tmp/serialization_comparison_ring.mem"
    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    rb = RingBuffer(capacity=1024, create=True, backing_file=backing_file)

    order = SAMPLE_ORDER
    t0 = time.perf_counter()
    for _ in range(n):
        rb.write_order(order)
        rb.read_order()
    elapsed = time.perf_counter() - t0

    for p in (backing_file, backing_file + ".lock"):
        if os.path.exists(p):
            os.remove(p)
    return n / elapsed


def bench_json_message_size() -> int:
    return len(json.dumps(SAMPLE_ORDER).encode("utf-8"))


def bench_pickle_message_size() -> int:
    return len(pickle.dumps(SAMPLE_ORDER))


def bench_struct_message_size() -> int:
    return len(pack_order(SAMPLE_ORDER))


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_N

    print("=" * 78)
    print("ChronosMatch -- Serialization Method Comparison")
    print(f"({n:,} round trips per method: encode + decode)")
    print("=" * 78)

    json_rate = bench_json(n)
    pickle_rate = bench_pickle(n)
    struct_rate = bench_struct(n)
    full_rb_rate = bench_full_ring_buffer(n)

    json_size = bench_json_message_size()
    pickle_size = bench_pickle_message_size()
    struct_size = bench_struct_message_size()

    print(f"\n{'Method':<38} {'Throughput':>16}  {'Serialization':>13}  {'Bytes/msg':>10}")
    print("-" * 82)
    print(f"{'JSON (dumps + loads)':<38} {json_rate:>13,.0f}/s  {'Yes':>13}  {json_size:>10}")
    print(f"{'Pickle (dumps + loads)':<38} {pickle_rate:>13,.0f}/s  {'Yes':>13}  {pickle_size:>10}")
    print(f"{'struct (pack + unpack, this proj.)':<38} {struct_rate:>13,.0f}/s  {'No':>13}  {struct_size:>10}")
    print(f"{'mmap + struct (full RingBuffer r/w)':<38} {full_rb_rate:>13,.0f}/s  {'No':>13}  {struct_size:>10}")
    print("=" * 78)

    struct_vs_json = struct_rate / json_rate
    struct_vs_pickle = struct_rate / pickle_rate
    print(f"\nstruct pack/unpack is {struct_vs_json:.1f}x faster than JSON, "
          f"{struct_vs_pickle:.1f}x faster than Pickle, for the same "
          f"encode+decode round trip.")
    print(f"Even the FULL IPC round trip (real shared-memory write + "
          f"read, lock included) sustains {full_rb_rate:,.0f} orders/sec "
          f"-- see audits/ipc_audit.py for the same claim proven across "
          f"two real OS processes at 1,000,000-order scale.")
    print("\nMessage size note: struct's fixed 29 bytes/order is smaller "
          f"than JSON's {json_size} and Pickle's {pickle_size} bytes for "
          "the identical order data, and -- unlike JSON/Pickle -- never "
          "varies with field values, which is what lets the ring buffer "
          "use fixed-size slots with no length-prefix framing at all.")
    print("=" * 78)


if __name__ == "__main__":
    main()
