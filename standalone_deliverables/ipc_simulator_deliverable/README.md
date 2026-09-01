# ChronosMatch — Data Pipeline (Person 2 deliverable)

Owner question this answers: **"Can we move huge volumes of orders between
processes without serialization becoming the bottleneck?"**

A zero-copy mmap ring buffer + binary wire protocol, and an asyncio market
simulator, benchmarked and cross-process-tested against the task's full
requirement list.

```
ipc/
├── protocol.py                    # binary Order format: struct.pack/unpack, fully documented
├── shared_memory.py                # mmap region + cross-process lock
├── ring_buffer.py                   # circular queue built on the above two
├── serialization_comparison.py     # JSON vs Pickle vs struct+mmap, measured
└── tests/
    └── test_ring_buffer.py        # 23 tests incl. 100k/1M-order real cross-process runs

simulator/
├── market_simulator.py             # asyncio firehose: realistic orders, bursts, price levels
├── load_test.py                     # graduated throughput sweep, finds the breakdown point
└── tests/
    └── test_market_simulator.py   # 17 tests
```

## Build & run

```bash
pip install pytest pytest-asyncio

pytest ipc/tests/ simulator/tests/ -v        # 40 passed, ~15-20s (includes a real 1M-order cross-process run)

python ipc/protocol.py                        # dump + explain the wire format
python ipc/serialization_comparison.py         # JSON vs Pickle vs struct throughput table
python simulator/market_simulator.py           # 3-second demo run
python simulator/load_test.py                  # graduated load test (10k...500k/sec)
```

## 1. mmap ring buffer

`ipc/shared_memory.py` (the mmap region + header + lock) and
`ipc/ring_buffer.py` (the circular-queue semantics on top of it) split
ownership of the task's list this way:

| Requirement | Owner |
|---|---|
| Shared memory layout | `SharedRingMemory`: `[HEADER][SLOT 0][SLOT 1]...[SLOT N-1]`, header = `capacity, read_ptr, write_ptr, occupancy` (`<IIII`, 16 bytes) |
| Producer position | `write_pointer` in the header — advanced by `write_order()` |
| Consumer position | `read_pointer` in the header — advanced by `read_order()` |
| Buffer capacity | fixed at creation, stored in the header, never changes |
| Wrap-around | both pointers advance via `(ptr + 1) % capacity` |
| Full-buffer behavior | `write_order()` checks `occupancy == capacity` first; returns `False`, writes nothing |
| Empty-buffer behavior | `read_order()` checks `occupancy == 0` first; returns `None`, reads nothing |
| Synchronization | `CrossProcessLock` — OS-native `fcntl.flock`/`msvcrt.locking` on a shared file path (works across independently-started processes, unlike `multiprocessing.Lock()`; auto-releases if a process dies mid-hold) |

**Honest design note on synchronization:** one lock protects both
`write_order()` and `read_order()` — correctness comes from serializing
every buffer access through a single mutex, not from a true lock-free
SPSC (single-producer/single-consumer) algorithm using atomic pointer
ops. That's a deliberate simplicity/robustness trade-off: it's what
`tests/test_ring_buffer.py::TestCrossProcess::test_throughput_degrades_at_very_small_capacity`
measures directly — at very small buffer capacities the two processes
toggle full/empty on almost every operation, and each transition costs
a real cross-process lock round-trip, so throughput scales down with
capacity in that regime (measured on this machine: an 8-slot buffer
sustains roughly two orders of magnitude less throughput than a
512-slot one). This is *why* production capacity (4096, used in
`audits/ipc_audit.py` and most tests here) is chosen much larger than
the minimum needed for correctness.

## 2. Binary order format

```
Order
├── Order ID    →  Q  (uint64, 8 bytes)
├── Side        →  c  (char,   1 byte,  'B' or 'S')
├── Price       →  d  (double, 8 bytes)
├── Quantity    →  I  (uint32, 4 bytes)
└── Timestamp   →  Q  (uint64, 8 bytes, nanoseconds)

Format string: "<QcdIQ"  →  29 bytes, fixed, every field always present.
"<" = little-endian AND no native struct padding, so 29 bytes is exact
and portable — see ipc/protocol.py's module docstring for the full
byte-offset table and why that matters.
```

No JSON, no Pickle, no Python dict crosses shared memory — only the
29-byte packed struct. `pack_order()`/`unpack_order()` are the only two
functions that touch `struct`; every other module imports them rather
than re-implementing packing.

## 3. Cross-process testing

`ipc/tests/test_ring_buffer.py::TestCrossProcess` — every scenario is a
**real `multiprocessing.Process`**, not a thread, verified by exit codes
and (where relevant) distinct PIDs:

| Required scenario | Test |
|---|---|
| 100k orders | `test_100k_orders_no_loss_no_duplication_correct_order` |
| 1M orders | `test_1m_orders_no_loss_no_duplication_correct_order` |
| Buffer wrap-around | `test_wraparound_under_real_cross_process_load` (512-slot buffer, 50k orders → ~100 full wraps under real concurrent load) |
| Simultaneous producer/consumer | `test_simultaneous_producer_and_consumer_overlap_in_time` (asserts the consumer's first read timestamp precedes the producer's last write timestamp — genuine overlap, not accidental serialization) |
| Overflow | `TestOverflowUnderflow` (single-process) + implicitly exercised throughout every cross-process run via backpressure retries |
| Underflow | `TestOverflowUnderflow::test_read_from_empty_buffer_returns_none_and_does_not_corrupt_state` + the same backpressure pattern from the consumer side |
| Process startup/shutdown | `test_process_startup_and_shutdown_is_clean` (asserts `exitcode == 0` for both, no hang, no orphan) |

Every cross-process test checks completeness (every order id received,
via set difference, not just a count — a count alone could hide N lost
and N duplicated cancelling out) **and** ordering (received list equals
the exact sequence written — this is a single-producer/single-consumer
queue, so ordering must be exact).

## 4. Market simulator

`simulator/market_simulator.py` — `MarketSimulator`, asyncio-driven,
`start()`/`stop()`/`pause()`/`resume()`. Realistic generation:

- **Buy/Sell** — configurable split, default 50/50.
- **Prices** — snapped to discrete *tick-aligned levels* around a
  mid-price (`round(mid + offset * tick, 2)`), not a continuous uniform
  draw — this is what makes many orders land on the *same* price, i.e.
  actual order-book depth, the way a real market works.
- **Quantities** — random within a configurable range.
- **Order IDs** — monotonically increasing, unique per order.
- **Bursts** — each 10ms tick, a small probability of entering a burst
  window (default: multiplies the effective rate 8x for 0.5s) — a real
  wave of volume, not a constant steady-state rate.

Throughput technique: batches writes per 10ms tick instead of sleeping
once per order (a naive per-order `asyncio.sleep()` loop is capped by
timer-wakeup frequency — measured elsewhere in this project at ~55k
wakeups/sec regardless of how fast the actual work is — not by real
work speed).

## 5. Load testing

`simulator/load_test.py` sweeps target rates and reports where
achieved throughput starts falling behind. One real run on this
sandbox machine:

```
  Target/sec   Achieved/sec  % of target     Written    Dropped
------------------------------------------------------------------------------
      10,000          9,973        99.7%      20,000          0
      50,000         49,857        99.7%     100,000          0
     100,000         99,283        99.3%     199,000          0
     150,000        121,333        80.9%     243,000          0
     200,000        123,802        61.9%     252,000          0
     300,000        125,819        41.9%     262,145          0

Throughput breaks down at target=200,000/sec: achieved only 123,802/sec
(61.9% of target). Highest target rate still sustained above threshold:
150,000/sec (121,333/sec achieved, 80.9% of target).
```

Consistent with the spec's 100,000/sec target being comfortably
achievable (99.3% of target hit) and with this project's other
independent throughput measurements (the two-process IPC audit
separately measures ~130k/sec at 1,000,000-order scale) landing in the
same ballpark for where the ceiling sits on this class of machine.

## 6. IPC audit — serialization comparison

`ipc/serialization_comparison.py` — measures pure encode+decode
round-trip cost for the same order, three ways, plus the full IPC
round trip (lock + header + slot) for the struct/mmap method actually
used. One real run on this machine (500,000 round trips/method):

```
Method                                       Throughput  Serialization   Bytes/msg
----------------------------------------------------------------------------------
JSON (dumps + loads)                         228,107/s            Yes          94
Pickle (dumps + loads)                       705,778/s            Yes          92
struct (pack + unpack, this proj.)         1,592,657/s             No          29
mmap + struct (full RingBuffer r/w)          197,069/s             No          29
```

`struct` pack/unpack alone is **~7x faster than JSON, ~2.3x faster than
Pickle** for the identical data, and produces a message less than a
third the size (29 bytes vs. 92-94) — with no length-prefix framing
needed at all, since every message is the *same* fixed size. Even the
**full** IPC round trip (real shared-memory write + read, lock
included, not just serialization) sustains ~197k/sec single-process —
and `audits/ipc_audit.py` (in the wider ChronosMatch project this was
extracted from) proves the same zero-copy design sustains real
throughput across two actual OS processes at 1,000,000-order scale.

## Provenance

Like the matching-engine deliverable, this package was extracted and
hardened from a larger, more mature ChronosMatch codebase
(`shared/ring_buffer.py`, `shared/shared_memory.py`,
`shared/serializer.py`, `simulator/market_firehose.py` — already proven
at 1,000,000-order, two-real-process scale with zero data loss, see
`audits/ipc_audit.py` and `tests/test_cross_process_locking.py` there).
That existing IPC bus and its cross-process locking fix (a real bug:
`multiprocessing.Lock()` doesn't synchronize independently-started
processes) were reused as-is. What this package adds against this
task's specific requirement list: a fully documented binary-protocol
spec (`protocol.py`, previously undocumented byte layout), a measured
JSON/Pickle/struct comparison (didn't exist before), a graduated
load-test sweep that finds the actual breakdown point (previous
benchmarks only measured a single uncapped ceiling), and burst-capable
realistic order generation (previous generator used continuous
uniform pricing with no burst concept).
