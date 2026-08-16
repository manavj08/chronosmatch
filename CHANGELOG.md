# CHANGELOG

## Day 1 — Leader: project restructure + real ring buffer wiring

### Added
- `engine/` package — `order_book.py` moved here (was root `order_book.py`)
- `engine/tests/test_order_book.py` — 4 new tests confirming the engine
  now reads from the real shared-memory ring buffer
- `api/` package (empty scaffold — FastAPI app lands Day 8)
- `logging_service/` package (empty scaffold — lands Day 6)

### Changed
- `OrderBook` now reads orders from `shared.ring_buffer.RingBuffer`
  (Member A's real mmap-backed implementation) instead of the fake
  in-memory stub. `OrderBook(ring_buffer=...)` accepts an injectable
  buffer for testing; defaults to a real one.
- Renamed `shared/shared_interface.py` → `shared/shared_memory.py` to
  resolve a naming collision with the old root-level fake stub of the
  same name (`shared_interface.py`). The two files implemented
  completely different things and shared a name by accident.

### Removed
- Root `shared_interface.py` — the Day-1 fake in-memory stub. Superseded
  by Member A's real `shared/` package.
- Root `ring_buffer_stub.py` — superseded by `shared/ring_buffer.py`.
- Root `order_book.py` — moved to `engine/order_book.py`.
- `test_skeleton.py` — smoke test for the old fake stub trio
  (`shared_interface`, `ring_buffer_stub`, `simulator_starter`'s old
  path). Replaced by `engine/tests/test_order_book.py`, which tests
  the real wiring instead.

### Known breakage — NOT fixed today, flagged for owning member
- `simulator_starter.py` (root) still does
  `from shared_interface import write_order, next_order_id` — that
  module no longer exists. **This file is Member B's responsibility**
  per the assignment doc (their spec requires a full rewrite into
  `simulator/market_simulator.py` + `simulator/order_generator.py`
  anyway). Left untouched rather than patched, to avoid stepping on
  Member B's module before they start.
- `dashboard_starter.py` (root) still does `from order_book import
  OrderBook` — old path, now `engine.order_book`. Per Member C's
  assignment doc, the curses terminal dashboard is being replaced by
  the web dashboard (`frontend/`) entirely, so this file is likely to
  be retired rather than fixed. Flagged for Member C to decide.

### Tests
`pytest -v` → 9/9 passing (5 ring buffer, 4 engine).

## Day 2 — Leader + Member B + Member C (solo from here on)

**Ownership change:** Members B and C are no longer contributing.
All remaining work in the project — Leader's engine/API, Member B's
simulator/database, Member C's frontend wiring — is being completed
solo, one role's task per day going forward (see `TASKS.md` for the
revised 25-day plan).

### Leader — sorted order insertion
- `engine/order_book.py`: `insert_order()` now inserts each order into
  its correct sorted position using `bisect.insort()`, instead of a
  plain append.
  - `buy_side` stays sorted descending by price (best/highest bid at
    index 0)
  - `sell_side` stays sorted ascending by price (best/lowest ask at
    index 0)
  - Equal-price orders keep arrival order (time priority) since
    `insort` is stable relative to the sort key
- `get_top_levels()` docstring updated — it was already just a slice,
  but the slice is now genuinely sorted instead of insertion order
- Added `engine/tests/test_insert_order.py` — 5 new tests: descending
  buy sort, ascending sell sort, best-bid/best-ask at index 0, time
  priority at equal price, `depth` parameter behavior

### Member B — simulator config + order generation (new package)
- `simulator/config.py`: `ORDERS_PER_SECOND`, `PRICE_MIN`/`PRICE_MAX`,
  `MIN_QUANTITY`/`MAX_QUANTITY`, `BUY_PROBABILITY`, per spec
- `simulator/order_generator.py`: `generate_order()` builds one random
  order in the agreed shared format; `next_order_id()` gives
  incrementing ids. **Not yet wired to the ring buffer** — that's
  `market_simulator.py`'s `start_simulation()` etc., landing Day 4.
- Added `simulator/tests/test_order_generator.py` — 5 tests: required
  keys, valid side, price/quantity within configured range,
  incrementing ids

### Member C — frontend test scaffold
- Added `frontend/tests/test_pages_exist.py` — structural tests since
  there's no JS build tooling in this project (plain pytest against
  the static HTML): all 7 pages exist, dashboard references its
  chart/websocket/dashboard scripts, all pages have a responsive
  viewport meta tag
- **Real finding, not a test bug:** `dashboard.html` never includes a
  `<script src="js/api.js">` tag at all, even though the file exists.
  Documented as `test_api_js_not_yet_linked_in_dashboard` rather than
  silently added, since `api.js` is still empty — linking an empty
  script now would be premature. Real wiring + the `<script>` tag both
  land together on Day 15.

### Tests
`pytest -v` → 23/23 passing (5 ring buffer, 4 engine wiring, 5 sorted
insertion, 3 frontend structure, 5 order generation, 1 documented gap).

### Notes for Day 3
`match_order()` is still a placeholder — it calls `insert_order()`
and nothing else. Day 3 adds real price-time priority matching on top
of this sorted structure (best bid/ask are now always at index 0,
which is what Day 3's crossing logic will check).

## Day 2 (revised) — Major pivot: company spec received

**The company issued the official project spec** ("ChronosMatch —
Zero-Copy High-Frequency Trading Engine"). This replaces the earlier
self-directed FastAPI + web-dashboard plan. See `TASKS.md` for the
full rationale and the revised 25-day plan mapped to the spec's
4-week structure.

### Archived (not deleted)
- `api/`, `frontend/`, `logging_service/` moved to
  `archive_web_dashboard/`. This work is preserved for reference but
  is no longer the active deliverable — the spec requires a curses
  terminal dashboard, not a web dashboard.

### Confirmed spec-compliant, no changes needed
- `shared/` (Member A's ring buffer): already uses raw `struct.pack`
  binary serialization over `mmap`, not JSON/Pickle. This satisfies
  the spec's Week 1 "Zero-Copy IPC Bus" requirement as originally
  built.

### Added — Cython matching engine (new `matching_engine/` package)
- `order_book.pyx`: `OrderBookCython` — Limit Order Book with sorted
  insertion. Order fields typed with C types (`int64_t`, `double`,
  `char`) internally; comparisons during insertion happen at the C
  level via a manually written binary search (not Python's `bisect`,
  which isn't usable the same way against C-typed comparisons).
- `setup.py`: build script using `Cython.Build.cythonize`. Compiles
  to a real platform-specific `.so` — verified working:
  ```
  cd matching_engine && python setup.py build_ext --inplace
  ```
- `matching_engine/tests/test_order_book_cython.py` — 5 tests,
  including a direct cross-check that the compiled Cython version and
  the pure-Python reference (`engine/order_book.py`) produce identical
  sort ordering for the same input.
- `.gitignore` updated to exclude compiled artifacts (`.so`, `.pyd`,
  generated `.c`, `build/`) — these are platform-specific build
  outputs, not source.

### Notes
- `engine/order_book.py` (pure Python) is being kept, not deleted —
  it now serves as the correctness reference the Cython version is
  checked against, per `test_matches_pure_python_reference_ordering`.
- Matching (crossing) logic itself is still a placeholder in the
  Cython version too — Day 5 per the revised plan.
- The asyncio market firehose (Week 1, second track) and curses
  dashboard (Week 2) have not started yet — see `TASKS.md`.

### Tests
`pytest -v` → 28/28 passing (23 previous + 5 new Cython engine tests).

## Demo tooling (supports Day 2 deliverables)

### Added
- `setup_demo.py` — one-command wrapper to build the Cython extension
  from the project root
- `run_demo.py` — live two-process demo: a real generator process
  writes orders into the shared-memory ring buffer, a real matcher
  process (separate PID) reads from the same memory region and feeds
  the compiled Cython order book. Prints best bid/ask live as orders
  arrive.
- Verified: ran end to end, both processes exit cleanly, correct order
  count for the configured duration/rate.

Honestly scoped in the script's own docstring: this demonstrates
zero-copy IPC + the compiled Cython engine running, not yet real
trade matching, the curses dashboard, or latency numbers — those land
on their scheduled days per `TASKS.md`.

## Day 3 — Member B: asyncio market firehose

### Added
- `simulator/market_firehose.py`: `MarketFirehose` class — async
  order generation and ring-buffer writing, per spec ("asyncio
  script that blasts mock trade orders into the IPC bus").
  - `start()` / `stop()` / `pause()` / `resume()` matching the shape
    the spec calls for (`start_simulation()` etc.)
  - Bounded retry-with-backoff when the ring buffer is full, instead
    of blocking forever or busy-looping
  - `get_stats()`: orders written/dropped, elapsed time, target vs.
    actual achieved rate — needed for Day 4's throughput push
- `pytest.ini`: `asyncio_mode = auto`, so `@pytest.mark.asyncio` tests
  work without per-test boilerplate
- `simulator/tests/test_market_firehose.py` — 6 tests: start/stop
  writes orders, pause halts generation, resume continues it, stats
  shape and rate sanity, double-start is a no-op, backoff behavior
  under a full buffer

### Notes — honesty about scope
The spec's phrase "simulating a firehose of Nasdaq/NYSE financial
tick data" via a websocket client does NOT mean this connects to a
real market data feed — there isn't one in scope for this project.
What's actually built is the asyncio *architecture* a websocket
client would use (single event loop, non-blocking, many "ticks" in
flight) driving the same local random order generator from Day 2
(`order_generator.py`, unchanged). Documented directly in
`market_firehose.py`'s module docstring so this isn't misrepresented
later.

`order_generator.py` itself was not modified — `generate_order()` is
still the function that builds one random order. `market_firehose.py`
is what drives it asynchronously at scale and writes results into the
ring buffer; that wiring didn't exist before today.

### Tests
`pytest -v` → 34/34 passing (28 from Day 1-2 + 6 new asyncio firehose
tests). Requires the Cython extension to be built first (`python
setup_demo.py`) — without it, `matching_engine/tests/` skips cleanly
and the count is 29/29 + 1 skipped instead.

### Notes for Day 4
Today's smoke test (`python -m simulator.market_firehose`) ran 50
orders/sec deliberately, for easy verification. Day 4 pushes toward
the spec's 100,000 orders/sec target and measures what's actually
achievable — the retry/backoff design here is what will be stress
tested.

## Day 4 — Member B: throughput push, found and fixed a real bottleneck

### What was measured
Added `benchmarks/throughput_benchmark.py` — measures each layer of
the pipeline separately instead of only an end-to-end number, so any
slowdown can be traced to its actual source:
1. `generate_order()` alone (pure Python, no IPC)
2. `RingBuffer.write_order()` alone (pre-built orders)
3. Both together, synchronously (no asyncio)
4. `MarketFirehose` end-to-end (asyncio, uncapped target rate)

### What it found
On the first run, the synchronous path (layer 3) sustained roughly
190,000-200,000 orders/sec, but the asyncio firehose (layer 4) only
achieved ~55,700 orders/sec — asyncio was making things SLOWER than
the same work done synchronously, not faster.

Root cause, isolated with a small standalone test: `asyncio.sleep()`
called once per single order has real per-call scheduling overhead
(event loop timer heap, wakeup), independent of how short the
requested delay is. Sleeping once per order caps total throughput at
whatever rate asyncio's timer scheduling can sustain — around
147,000 sleep-calls/sec on the benchmark machine — regardless of how
fast the actual order generation and IPC write are.

### The fix
Rewrote `MarketFirehose._run()` (`simulator/market_firehose.py`) to
batch orders per event-loop tick (10ms) instead of sleeping once per
individual order: compute how many orders the target rate implies for
one tick, write that whole batch, then sleep once per tick instead of
once per order.

A second bug showed up once batching was in place: at a 100,000/sec
target, actual throughput was still only ~75,600/sec, because the
loop slept for the FULL tick duration regardless of how long the
batch itself took to process — eating into the next tick's budget.
Fixed by measuring the batch's actual elapsed time and sleeping only
for whatever remained of the 10ms tick.

### Results (this benchmark machine — single CPU core sandbox)
| Target rate | Before fix | After fix |
|---|---|---|
| Uncapped (ceiling test) | ~55,700/sec | ~140,000-210,000/sec (varies by run) |
| 100,000/sec (spec target) | ~75,600/sec | ~96,000-99,700/sec, consistent across repeated runs |

### Honesty about what this number means
This is a single-core sandbox, not dedicated trading hardware, and
not a substitute for real benchmarking on target deployment
infrastructure — documented directly in
`benchmarks/throughput_benchmark.py`'s module docstring. What this
result actually demonstrates: the pipeline architecture (asyncio
generation -> zero-copy mmap write) can sustain the spec's 100,000
orders/sec target on modest hardware once an actual bottleneck (naive
per-order scheduling) is found and fixed — not a guarantee of that
number on any particular production machine.

### Added
- `benchmarks/throughput_benchmark.py` — layer-by-layer benchmark script
- `simulator/tests/test_firehose_throughput.py` — 2 automated
  regression tests: (1) throughput stays well above the old
  pre-batching ceiling, so a future change can't silently reintroduce
  the per-order-sleep bottleneck; (2) actual rate lands reasonably
  close to a configured target, catching a gross undershoot like the
  tick-timing bug above. Thresholds set conservatively to avoid CI
  flakiness on slower machines — these are regression guards, not
  precise performance assertions.

### Tests
`pytest -v` → 36/36 passing (34 previous + 2 new throughput tests).
All Day 3 tests (`test_market_firehose.py`) still pass unmodified
after the batching rewrite — pause/resume/stats/backoff behavior is
unchanged, only the internal scheduling strategy changed.

## Day 5 — Leader: real price-time priority matching in the Cython engine

### Added
- `matching_engine/order_book.pyx`: `match_order()` — real crossing
  logic, replacing the Day 2-4 placeholder that only called
  `insert_order()`. Algorithm:
  1. Incoming Buy checks the best (lowest) resting Sell price;
     crosses while ask <= buy price.
  2. Incoming Sell checks the best (highest) resting Buy price;
     crosses while bid >= sell price.
  3. Fill quantity = min(incoming remaining, resting order quantity).
  4. Fully consumed resting orders are removed from the book;
     partially filled resting orders are reduced in place and keep
     their price-time priority position.
  5. Any leftover incoming quantity is inserted onto the book via the
     existing sorted `insert_order()`.
  - Trade price always executes at the RESTING order's price (the
    better price), not the incoming order's price — verified by
    `test_buy_matches_at_better_price_than_offered`.
  - `_record_trade()` and `get_last_trade()` ported from the
    pure-Python reference's shape, so trade dicts match across both
    engines.
- `matching_engine/tests/test_matching.py` — 12 tests: full match
  (both directions), partial match (both directions), multi-level
  book walking (large order consumes several price levels), price
  limit enforcement (order stops matching once price no longer
  crosses, even with cheaper/dearer orders still on the book beyond
  that), no-cross resting, matching against an empty book, time
  priority at equal price, trade id sequencing, `get_last_trade()`
  correctness.
- `run_demo.py` updated: the matcher process now calls
  `match_order()` instead of `insert_order()`, and prints each trade
  as it executes. Manually verified — a real run produced 30 trades
  from 50 generated orders across two real OS processes, including
  visible multi-fill matches where one incoming order consumed
  several resting orders in sequence.

### Notes
The pure-Python reference (`engine/order_book.py`) was NOT given
matching logic today — its own docstring scopes it as the Day 2
correctness baseline for sorted *insertion* specifically, and the
revised 25-day plan (Day 2 pivot) scopes real matching to the Cython
engine, which is the actual spec deliverable. Extending the Python
reference with matching too was considered but deferred as
out-of-scope for today rather than done silently.

Cython matching still allocates trade dicts as Python objects — this
is fine for correctness (today's goal) but not yet GC-safe under the
spec's "zero pauses during a trade" requirement. That's explicitly
Day 6's job ("Strip remaining Python object interaction from the
matching loop; confirm no GC triggers during a match").

### Tests
`pytest -v` → 48/48 passing (36 previous + 12 new matching tests).
All Day 2 Cython tests (`test_order_book_cython.py`) still pass
unmodified.

## Day 6 — Leader: GC-free matching engine (C struct arrays), found and fixed a memory corruption bug

### What changed
Full internal rewrite of `matching_engine/order_book.pyx`. Through
Day 5, orders were stored as Python dicts inside Python lists —
every insert/match touched real Python objects (dict lookups, list
`.insert()`/`.pop(0)`, a fresh dict per trade). That's exactly what
the garbage collector tracks, so the spec's "guarantee the GC never
triggers during a trade" requirement was NOT actually met by Day 5,
despite the comparisons already using C types.

Day 6 replaces internal storage with two fixed-capacity C arrays of
a plain `COrder` struct (`_buy_orders`, `_sell_orders`), allocated
once via `PyMem_Malloc` in `__cinit__` and freed once in
`__dealloc__` — no PyObject anywhere in them. A third C array
(`_trades_c`) holds recorded trades the same way. The actual
insertion (`_insert_c`) and matching (`_match_c`) logic now operate
ENTIRELY on these arrays — no dict access, no list method calls, no
per-trade object allocation — and are marked `nogil`, since they make
no Python C-API calls.

The public API (`insert_order()`, `match_order()`, `get_top_levels()`,
`get_last_trade()`, the `buy_side`/`sell_side`/`trades` properties)
still accepts and returns Python dicts, for compatibility with every
existing test and `run_demo.py`. Converting a C struct to a dict for
a caller who explicitly asked for one happens ONLY at that edge, once
per call — never inside the matching loop itself. This is the
standard pattern for bridging a GC-free hot path to a Python-friendly
public API, and is documented at length in the module's own docstring.

### A real bug found while writing the verification test
Writing `test_gc_safety.py`'s 200,000-iteration stress test surfaced
a genuine, serious bug: the original `_insert_c()` had no bounds
check against `MAX_BOOK_DEPTH` (100,000). An early version of the
stress test's order mix caused one side of the book to accumulate
unbounded resting inventory, silently writing past the end of the
pre-allocated C array once it exceeded capacity — this corrupted
adjacent heap memory without crashing immediately. The crash only
surfaced later, on a completely unrelated subsequent call
(`Fatal Python error: Aborted`), which made it non-obvious at first
that the real cause was upstream in the earlier loop.

Root cause traced by inspecting book state after the stress loop
(`len(book.sell_side)` = 100,001 — one over capacity) rather than
guessing from the crash site. Fixed two things:
1. `_insert_c()` now checks capacity and returns `False` (dropping
   the order) instead of writing out of bounds — documented as a
   placeholder policy, not a real capacity-management design (a
   production version would need to reject upstream, widen depth, or
   evict a price level instead of silently dropping).
2. The stress test itself was redesigned so every iteration actually
   matches against a seeded, effectively-infinite resting order on
   both sides, instead of letting unmatched orders pile up as new
   resting inventory indefinitely.

A dedicated regression test (`test_book_depth_capacity_guard_prevents_overflow`)
now reproduces the overflow scenario directly and confirms the guard
holds and the engine stays in a valid, usable state afterward.

### Added
- `matching_engine/tests/test_gc_safety.py` — 5 tests:
  - Allocated-block-count comparison (pure-C matching path vs. a
    no-op baseline of the same iteration count) over 200,000 cycles
  - `gc.get_stats()` collection-count comparison with the collector
    disabled, confirming no reliance on GC cleanup
  - Correctness spot-check of the pure-C entry point
    (`run_c_only_matching_cycle`)
  - Correctness spot-check of the public dict-based API, confirming
    the internal rewrite didn't change external behavior
  - Regression test for the capacity-overflow bug described above
- `run_c_only_matching_cycle()`: new public method that runs a full
  insert-or-match cycle using ONLY the C struct path — no dict is
  created or read anywhere in the call — used by the GC-safety tests
  to measure the actual hot loop rather than the convenience wrapper.

### Verified
- All 17 pre-existing Cython tests (Day 2 + Day 5) pass UNMODIFIED
  against the rewritten internals — the public dict-based behavior is
  fully preserved.
- `run_demo.py` re-run end to end after the rewrite: two real
  processes, real trades executing, no behavior change from the
  user's perspective.
- Rough throughput check of the pure-C path alone (bypassing IPC
  entirely): ~2.39 million matching cycles/sec on this benchmark
  machine. Not directly comparable to Day 4's ~100k/sec end-to-end
  IPC throughput number — this measures the matching engine in
  isolation, not the full pipeline.

### Tests
`pytest -v` → 53/53 passing (48 previous + 5 new GC-safety tests).

## Day 7 — Member C: real curses terminal dashboard

### Added
- `dashboard/live_dashboard.py`: `run_dashboard()` — a real, separate
  OS process that reads orders from the shared-memory ring buffer,
  matches them with the real compiled Cython engine, and renders a
  live curses display: top 5 bid/ask levels, last trade, running
  orders-processed/trades-matched counts, and highlighted "whale"
  trades (quantity >= 50, per spec: "visually highlight when a
  massive Whale order clears multiple price levels"). Replaces the
  old `dashboard_starter.py` skeleton, which is now removed.
- `format_whale_line()` / `update_whale_lines()`: whale-detection and
  rolling-history logic extracted into pure functions with no curses
  dependency, specifically so they're unit-testable.
- `run_dashboard_demo.py`: one-command runner — starts a silent
  generator process (no stdout prints, since curses owns the
  terminal) alongside the dashboard process.
- `dashboard/tests/test_dashboard_logic.py` — 7 tests covering whale
  detection (threshold boundary, mixed batches, newest-first
  ordering, history capping, empty-batch no-op).

### Testing note --- important limitation, stated honestly
This sandbox has no real TTY. `curses.wrapper()` requires terminal
control (`cbreak()`/`nocbreak()`) that fails outside one — confirmed
directly:
```
_curses.error: cbreak() returned ERR
```
This means the actual curses RENDERING could not be verified through
pytest in this environment. Two things were done instead:
1. The decision-making logic (whale detection, history management)
   was extracted into pure functions with no curses dependency, so
   THAT part has real automated test coverage (7 tests above).
2. The full dashboard was run through a pseudo-terminal (`script -qc`)
   to get a real TTY. This is genuine execution, not a mock — it
   produced real curses escape sequences, live-updating bid/ask
   values, incrementing order/trade counts, and multiple correctly
   formatted "WHALE:" highlight lines during a real run. Confirmed
   clean process exit (code 0) after the full configured duration,
   and no crash or orphaned processes when tested under an
   artificially narrow terminal.

This is real verification, but it is manual verification of one run,
not an automated regression test that runs on every future change —
worth knowing if this environment's TTY limitation isn't present
wherever this project runs next (a normal terminal on a dev machine
has a real TTY and `pytest` there could exercise curses directly, if
that coverage is wanted later).

### Removed
- `dashboard_starter.py` (repo root) — the pre-spec-pivot skeleton
  this file's own "WHAT TO DO NEXT" comments described building
  toward. That progression is now done for real in
  `dashboard/live_dashboard.py`.

### Tests
`pytest -v` → 60/60 passing (53 previous + 7 new dashboard logic
tests). Curses rendering itself verified manually via pseudo-terminal,
not via this count — see testing note above.

## Day 8 — Mid-Project Review: 1,000,000-order IPC audit, found and fixed TWO real bugs

### The task
Per spec: "Prove the zero-copy architecture works by sending 1M
orders between two Python processes without hitting the CPU
bottleneck of Pickling." Built `audits/ipc_audit.py`: a real producer
process and a real consumer process, communicating only through the
shared-memory ring buffer, verifying not just throughput but
completeness (every order arrives exactly once) and ordering (arrives
in the exact sequence written).

### Bug #1: the shared-memory lock never actually worked across processes
`shared/shared_memory.py`'s `SharedRingMemory.__init__` did
`self.lock = Lock()` (`multiprocessing.Lock`). That primitive only
synchronizes processes that share the SAME Lock object (e.g. passed
explicitly at process creation, or inherited via fork from a common
parent). Every process in this project instead independently
constructs its own `RingBuffer()` by opening the same backing file
path — so every process got its OWN separate Lock, providing zero
real cross-process mutual exclusion. This bug existed since Day 1.

**How it was found:** a 20,000-order manual test before writing the
real audit script. The consumer permanently stalled at 13,840 orders
received (out of 20,000) and never recovered — no exception, no
crash, just silently stuck. Root-caused by inspecting the actual
book/buffer state rather than guessing.

**First fix attempt (kept for the record, then improved):** a lock
file acquired via atomic exclusive creation (`os.O_CREAT | O_EXCL`).
Correct, but slow — real filesystem create/delete syscalls on every
single lock acquisition. Single-process timing: ~34,700 write+read
cycles/sec. The real two-process 1,000,000-order audit did not finish
within a 180-second timeout using this approach.

**Final fix:** genuine OS-native advisory file locking on an
already-open file descriptor — `fcntl.flock` on POSIX, `msvcrt.locking`
on Windows, selected automatically via `sys.platform`. This is the
standard, fast, atomic tool for this exact job on each platform, and
locks/unlocks an existing fd instead of creating/deleting a file each
time. Single-process timing improved to ~143,000 write+read cycles/sec
(a ~4x improvement over the file create/delete approach). Also
auto-releases if a process crashes while holding the lock, since the
OS drops the lock when the file descriptor closes — no stale-lock
cleanup logic needed, unlike the first attempt.

### Bug #2: multiprocessing.Queue deadlock (join-before-drain)
After fixing the lock, the audit script would run correctly (confirmed
via progress logging: all orders flowing through the ring buffer
correctly) but then hang indefinitely after the data transfer
finished. Root cause: the script called `producer.join()` and
`consumer.join()` BEFORE draining `result_queue` — a well-known
`multiprocessing` deadlock hazard. The consumer process puts a large
payload on the queue (a list of up to 1,000,000 order ids); the queue
is backed by a pipe with a background feeder thread, and if the
pipe's OS buffer fills before the parent reads it, the child blocks
trying to write while the parent's `join()` blocks waiting for the
child to exit — neither side can proceed.

**Fix:** drain the queue BEFORE calling `join()`, not after. Applied
in both `audits/ipc_audit.py` and the new regression test
(`tests/test_cross_process_locking.py`), with the reasoning documented
inline at both call sites so it doesn't get silently reintroduced by
a future edit that looks like a harmless reordering.

### Results (this benchmark machine — confirmed 1-core sandbox)
Two consecutive full 1,000,000-order runs:
| Run | Sent | Received | Missing | Duplicated | Ordered | End-to-end rate |
|---|---|---|---|---|---|---|
| 1 | 1,000,000 | 1,000,000 | 0 | 0 | True | 128,642/sec |
| 2 | 1,000,000 | 1,000,000 | 0 | 0 | True | 131,470/sec |

Both runs: `AUDIT PASSED`, exit code 0.

### Added
- `audits/ipc_audit.py` — the full 1,000,000-order audit, with live
  progress reporting and `IPC_AUDIT_ORDERS` env var override for
  smaller diagnostic runs
- `tests/test_cross_process_locking.py` — automated regression test
  at a CI-friendly 20,000-order scale (large enough to reliably
  reproduce the old race if it regressed, small enough to run in
  under a second), so a future accidental regression is caught by
  routine `pytest` runs, not only by remembering to run the full
  manual audit

### Verified after the fix
- All 60 pre-existing tests (Days 1-7) still pass unmodified
- `run_demo.py` and `run_dashboard_demo.py` re-run end to end,
  confirmed still working correctly with the new locking mechanism

### Tests
`pytest -v` → 61/61 passing (60 previous + 1 new cross-process
locking regression test).

### Honesty note
This is a single-core sandbox (confirmed via `nproc` = 1), not
dedicated hardware — same caveat as Day 4's benchmark. The ~130k/sec
end-to-end IPC rate is what this specific environment achieves once
both bugs were fixed, not a production hardware guarantee.
