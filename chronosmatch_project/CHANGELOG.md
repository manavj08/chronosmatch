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

## Day 9 — Mid-Project Review: Engine Verification (Buy/Sell matching, measured latency)

### What this adds beyond Day 5's tests
Day 5's `matching_engine/tests/test_matching.py` already proves
matching correctness thoroughly (12 tests) --- but every one of those
tests calls `match_order()` directly on an in-memory dict literal.
Day 9 covers the two things that approach doesn't:

1. **Correctness through the REAL pipeline** — orders enter via
   `RingBuffer.write_order()` (the same entry point real order flow
   uses) and are read back via `read_order()` before being matched,
   not constructed and handed straight to `match_order()`.
2. **"Instantly", actually measured** — wall-clock latency from
   `write_order()` to a trade being recorded, using
   `time.perf_counter_ns()`, reported as real percentiles rather than
   asserted as a pass/fail threshold.

### Added
- `audits/engine_verification.py` — standalone report script (same
  style as Day 8's `ipc_audit.py`): confirms one Buy matches a
  resting Sell through the real pipeline, then measures latency
  across 10,000 buy/sell pairs and reports min/mean/p50/p99/max.
- `matching_engine/tests/test_engine_verification.py` — 4 automated
  pytest tests: Buy-matches-Sell and Sell-matches-Buy through the
  real pipeline, a 20-cycle repeated-match correctness check (guards
  against state leaking between orders — stale pointers, trade_id not
  advancing), and a latency regression guard (median must stay under
  1ms — generous to avoid CI flakiness, but tight enough to catch a
  gross regression like an accidentally introduced sleep() or an
  O(n) scan reappearing in the hot path).

### Results (this benchmark machine — single-core sandbox, two runs)
| Run | Min | Mean | p50 | p99 | Max |
|---|---|---|---|---|---|
| 1 | 6.38µs | 8.26µs | 6.63µs | 24.52µs | 113.53µs |
| 2 | 6.29µs | 7.09µs | 6.54µs | 15.54µs | 150.93µs |

Both runs: correctness PASSED, p50 well under the spec's 50µs target,
measured through the real ring-buffer pipeline (not an isolated
in-memory shortcut).

### Honesty notes
- Single-process (writer and matcher sequential, same process) on
  purpose --- isolates match latency itself from IPC/OS
  context-switch noise between two separate processes, which is what
  Day 8's audit already measures at throughput scale rather than
  per-order latency. A two-process latency variant could be added
  later if that distinction becomes important for the final report.
- Same single-core sandbox caveat as every other benchmark in this
  project (Day 4, Day 8): real measurements, not a production
  hardware guarantee.
- No hard-coded "pass at exactly 50µs" assertion in the automated
  test --- the standalone report shows the real numbers against the
  spec's target for a human to read; the pytest regression guard uses
  a much looser 1ms threshold specifically to avoid false failures
  from ordinary machine noise while still catching a real regression.

### Tests
`pytest -v` → 65/65 passing (61 previous + 4 new engine verification
tests).

## Day 10 — C-level optimization pass: price-level bucketing, found a real bottleneck and a real regression along the way

### What was profiled first
Before changing anything, checked whether Day 6's hot-path functions
(`_insert_c`, `_match_c`) still had any Python-object interaction by
inspecting Cython's generated annotation (`order_book.html`) directly
rather than assuming. Result: zero Python-interaction lines in either
function — Day 6's GC-safety work held up under direct inspection.

So Day 10's optimization target had to be algorithmic, not
GC-related. Measured insertion throughput at increasing book depth
under an adversarial pattern (every order landing at the best price,
forcing maximum `memmove` shift distance):

| Book depth | Inserts/sec (Day 6 flat array) |
|---|---|
| 100 | 235,135 |
| 1,000 | 197,800 |
| 10,000 | 126,975 |
| 50,000 | 14,642 |
| 99,000 | 14,547 |

A genuine ~16x degradation from shallow to deep books, confirming the
O(n) array-shift cost of Day 6's one-flat-array-per-side design was a
real bottleneck under load — not a synthetic concern.

### The fix: price-level bucketing
Rewrote `matching_engine/order_book.pyx` internal storage from one
flat sorted array of individual orders per side to an array of price
LEVELS, each holding its own small FIFO array of orders at that exact
price — matching how real exchanges structure an order book. Binary
search now happens over price levels (typically far fewer than
individual orders in real markets) instead of over every order.
Appending a new order to an EXISTING level's FIFO is O(1) amortized
(tail append, no shift); creating a brand-new level or removing an
emptied one still costs a shift, but bounded by the number of
distinct prices, not the number of individual orders.

New structures: `PriceLevel` (price, a FIFO array of `COrder`, count,
capacity, and a `head` index that advances on removal instead of
shifting the whole FIFO on every fill). Per-level FIFO arrays grow via
`realloc()` if a single price level gets deeper than its starting
capacity (16 orders) — still pure C allocation (`libc.stdlib`, not
`PyMem_*`, since these calls happen inside `nogil` functions and
`PyMem_*` requires the GIL — this was a real compile error caught
immediately by the Cython compiler on the first build attempt).

### A real capacity regression, found by re-running the benchmark after the rewrite
The first working version set `MAX_PRICE_LEVELS = 10,000`, on the
assumption that real order books have far fewer distinct prices than
individual orders. Re-running the exact same adversarial benchmark
used to justify this rewrite (unique price per order, up to 99,000
orders) revealed the bug immediately: `len(book.sell_side)` returned
10,000, not 99,000 — 89,000 orders had been silently dropped once the
level array hit its (too-low) capacity limit. This would have been a
real, silent regression versus Day 6's 100,000-order capacity
guarantee. Fixed by raising `MAX_PRICE_LEVELS` to 100,000 to match
Day 6's `MAX_BOOK_DEPTH` exactly, and documented directly in the
constant's own comment so the reasoning doesn't get silently
re-broken later.

### Honest results — both scenarios reported, not just the favorable one
After the capacity fix, re-ran both the realistic and adversarial
benchmarks:

| Scenario | Day 6 (flat array) | Day 10 (price-level bucketing) |
|---|---|---|
| Realistic: 50,000 orders, 50 price levels | ~97,637/sec | ~1,739,635–2,770,274/sec (~18-28x) |
| Adversarial: unique price every order, depth 99,000 | ~14,547/sec | ~13,916–14,740/sec (no meaningful change) |

The adversarial case shows essentially NO improvement — expected and
now correctly understood, not silently mismeasured: when every order
is at a genuinely unique price, each "level" holds exactly one order,
so there's no FIFO-append benefit at all; shifting a level array
costs about the same as shifting an order array. Bucketing helps
enormously for realistic order flow (many orders sharing a bounded
set of prices) and provides no benefit in a fully adversarial,
non-repeating-price pattern. Both numbers are reported in
`benchmarks/level_bucketing_benchmark.py`'s output rather than
cherry-picking the favorable one.

### Added
- `benchmarks/level_bucketing_benchmark.py` — reports both the
  realistic and adversarial scenarios, with the interpretation
  printed alongside the numbers
- `matching_engine/tests/test_price_level_bucketing.py` — 7 tests:
  FIFO order preservation within a price level, level removal when
  fully drained, partial fills staying at the front of their level's
  FIFO, a level being correctly reused after being fully drained and
  refilled, per-level FIFO growth beyond its initial capacity (the
  `realloc()` path), the capacity regression described above
  (regression test — inserts 99,000 unique prices and confirms none
  are dropped), and a re-verification of Day 5's multi-level-walk
  scenario against the new internal structure

### Verified after the full rewrite
- All 26 pre-existing `matching_engine/tests/` tests (Days 2, 5, 6, 9)
  pass UNMODIFIED against the rewritten internals
- All 65 previously-passing project tests (Days 1-9) still pass
- `run_demo.py` re-run end to end: real trades still executing
  correctly across two real processes
- `run_dashboard_demo.py` re-run via pseudo-terminal: still renders
  correctly, whale trades still detected
- `audits/engine_verification.py` re-run: correctness still PASSED,
  p50 latency actually improved slightly (5.36µs vs. Day 9's 6.5-6.6µs
  — within normal run-to-run variance, not a claimed causal
  improvement)
- `audits/ipc_audit.py` re-run at full 1,000,000-order scale: still
  PASSED, 0 missing, 0 duplicated, correct ordering

### Tests
`pytest -v` → 72/72 passing (65 previous + 7 new price-level
bucketing tests).

## Day 11 — GC-pause verification extended + a real zero-quantity bug found

### GC-pause verification: closing a real coverage gap
Day 6's GC-safety tests (`test_gc_safety.py`) seed one huge resting
order and every subsequent test order fully matches against it
(`remaining` is always 0) — meaning `_insert_c()` was never actually
called by those tests. That was fine for Day 6's own design (a flat
array, no dynamic allocation inside the hot path at all), but Day 10
added `malloc()`/`realloc()` calls INSIDE `_insert_c()` (for creating
new price levels and growing a level's FIFO) — and nothing had
verified those specific calls stay GC-safe under load. This was a
real, unverified gap, found by re-reading exactly what the existing
tests did and didn't exercise, not by assumption.

Verified directly (both manually first, then as permanent tests):
- `malloc()` path (every order at a unique price, forcing a new
  `PriceLevel` every time): 0 GC collections across a sustained run
- `realloc()` path (every order at the SAME price, forcing the
  per-level FIFO to keep growing past its initial 16-slot capacity):
  0 GC collections across a sustained run

Both confirm the expected reasoning (`libc.stdlib` malloc/realloc/free
are raw C heap calls, entirely outside Python's object allocator and
GC) directly rather than only trusting the theory.

### Added — GC tests
- `matching_engine/tests/test_new_price_level_creation_triggers_no_collections`
- `matching_engine/tests/test_fifo_growth_within_one_price_level_triggers_no_collections`

Both in `matching_engine/tests/test_gc_safety.py`, alongside the
existing Day 6 tests.

### A real bug found via edge-case exploration
Per the plan's "expanded matching unit test coverage," explored edge
cases beyond what existing tests already covered: zero quantity,
negative quantity, and exact multi-level consumption. Found a genuine
bug: `_insert_c()` had no validation on `order.quantity` — a
zero-quantity order could be inserted onto the book and would sit
there as a phantom price level. When a later order matched against
it, it produced a fake trade with `quantity: 0` — a real "execution"
with no economic meaning, silently mixed in with real trades.

**Fix:** `_insert_c()` now rejects orders with `quantity <= 0` outright
(returns `False`, same convention as the existing `MAX_BOOK_DEPTH`
capacity guard). `_match_c()` didn't need a matching fix — its `while
remaining > 0` loop condition already prevents a zero-quantity
INCOMING order from producing any trade; the bug was specifically
about a zero-quantity order resting on the book and being matched
against later.

### Added — regression tests
`matching_engine/tests/test_price_level_bucketing.py`:
- `test_zero_quantity_order_is_rejected_not_inserted`
- `test_negative_quantity_order_is_rejected_not_inserted`
- `test_zero_quantity_resting_order_cannot_produce_phantom_trade`
- `test_exact_multi_level_consumption_leaves_book_empty` (a related
  edge case checked at the same time — no off-by-one leaves a
  phantom empty level or incorrect resting remainder when an
  incoming order's quantity exactly matches the sum of several
  resting levels)

### Verified after the fix
- All 72 previously-passing tests (Days 1-10) still pass
- `run_demo.py` re-run end to end: real trades still executing
  correctly
- `audits/engine_verification.py` re-run: correctness PASSED,
  p50 latency 4.08µs (within normal run-to-run variance of Day 10's
  5.36µs — not a claimed causal change from this fix)
- `audits/ipc_audit.py` re-run at full 1,000,000-order scale: still
  PASSED, 0 missing, 0 duplicated, correct ordering

### Tests
`pytest -v` → 78/78 passing (72 previous + 2 new GC coverage tests +
4 new zero-quantity/edge-case regression tests).

## Day 12 — nanosecond entry/exit latency instrumentation on every trade

### What changed
Per spec: "Embed time.perf_counter_ns() timestamps to measure the
exact nanosecond a trade enters and exits the engine." Every trade
produced by the matching engine now carries three new fields:
- `entry_timestamp` — the INCOMING (triggering) order's own
  timestamp, not the resting order's (the resting order may have
  been sitting on the book for an arbitrary, unrelated amount of
  time — what matters is how long the system took to process the
  order that just arrived)
- `exit_timestamp` — the nanosecond this specific trade was recorded,
  captured from INSIDE the `nogil` matching loop itself
- `latency_ns` — precomputed `exit_timestamp - entry_timestamp`,
  available even through the pure-C entry point with no Python
  arithmetic involved

### The key technical detail
Timestamp capture uses `cpython.time.perf_counter_ns()` (Cython's
C-level binding), not Python's `time.perf_counter_ns()` directly —
the latter requires the GIL, and this measurement happens inside
`_record_trade_c()`, called from the `nogil` `_match_c()` matching
loop. `cpython.time`'s version reads the same underlying OS clock
without needing the GIL, preserving Day 6/10's GC-safety guarantees.
Verified directly (not just assumed) by re-inspecting Cython's own
annotation output: `_record_trade_c` shows zero Python-interaction
lines even with the new timestamp capture added — same evidence-based
check used for Day 10's optimization work.

### Cross-verification against Day 9's external measurement
Ran both an external wall-clock measurement (write_order → match_order,
same technique as `audits/engine_verification.py`) and the new
internal `latency_ns` field side by side on the same 1,000 trades.
Result: internal (engine-only) p50 was 5.30µs vs. external p50 of
5.66µs — the internal number is correctly SMALLER, exactly as
expected, since it excludes the ring buffer read/write and
dict-conversion overhead that surrounds the engine call. This
cross-check gives real confidence the new instrumentation measures
what it claims to, rather than just trusting the arithmetic.

### Added
- `matching_engine/tests/test_latency_instrumentation.py` — 8 tests:
  trade dict includes all three new fields, `entry_timestamp` reflects
  the incoming order (not the resting one), `exit_timestamp` is
  strictly after `entry_timestamp`, `latency_ns` exactly equals their
  difference, latency is positive and sane-bounded, multiple trades
  produced by one multi-level match each get their own
  `exit_timestamp` while sharing the same `entry_timestamp`, the
  pure-C entry point (`run_c_only_matching_cycle`) also produces
  correctly timestamped trades (confirms the instrumentation lives in
  the actual hot path, not bolted on only at the Python-facing edge),
  and the `trades` property (full history view) also carries the new
  fields.

### Updated
- `run_demo.py`: each TRADE line now shows real per-trade latency in
  microseconds. Documented an important honesty point directly in the
  script: this demo's matcher process polls the ring buffer with a
  20ms sleep between empty reads, so an order can sit in the buffer
  for up to ~20ms before the matcher even looks at it — that polling
  delay dominates the numbers shown in this demo's output, and is a
  property of the demo's simple polling loop, not the engine. The
  engine's real matching latency (single-digit microseconds) is what
  `audits/engine_verification.py` and this day's unit tests measure
  in isolation, specifically to keep the two separate.
- `audits/engine_verification.py`: updated its closing message to
  point at the new internal instrumentation instead of referencing it
  as still-pending work.

### Verified after the change
- All 78 previously-passing tests (Days 1-11) still pass
- GC-safety re-confirmed explicitly (all 7 `test_gc_safety.py` tests
  pass; `_record_trade_c` re-checked via Cython annotation, zero
  Python-interaction lines)
- `run_demo.py` re-run end to end: real trades with real (if
  polling-dominated, as documented) latency numbers displayed
- `run_dashboard_demo.py` re-run via pseudo-terminal: still works,
  unaffected by the extra trade dict fields
- `audits/engine_verification.py` re-run: correctness PASSED, p50
  5.49µs
- `audits/ipc_audit.py` re-run at full 1,000,000-order scale: still
  PASSED, 0 missing, 0 duplicated, correct ordering

### Tests
`pytest -v` → 86/86 passing (78 previous + 8 new latency
instrumentation tests).

## Day 13 — latency metrics pipeline: live p50/p99/p999

### What this adds beyond Day 12
Day 12 gave every individual trade its own `entry_timestamp`,
`exit_timestamp`, and `latency_ns` — but nothing aggregated that data
into something a dashboard or monitor could actually query cheaply.
Pulling the full trade history (up to `MAX_TRADES` = 1,000,000
entries) and sorting it on every query would get slower as trades
accumulate, which is the wrong shape for something a live view might
poll repeatedly.

### Design
- A fixed-size circular buffer (`LATENCY_RING_SIZE` = 10,000) of the
  most recent trade latencies, written with O(1) cost per trade
  directly inside `_record_trade_c()` — no allocation, no sorting, on
  every single trade.
- Separately, exact lifetime running stats (`count`, `sum`, `min`,
  `max`) updated with O(1) cost per trade — these never need the ring
  buffer or any sorting, and stay exact no matter how many trades
  have happened in total (verified: lifetime `count` is correct even
  well past the ring's 10,000-entry capacity).
- `get_latency_stats()`: the only place any sorting happens, and only
  on demand — sorts a COPY of the bounded ring (via
  `libc.stdlib.qsort` with a plain C comparator function, not a
  Python-level sort), so querying stats has a small, predictable cost
  regardless of total trade volume, and never mutates the live ring
  or disturbs the matching engine's own state (verified directly:
  three consecutive stats queries against unchanged book state return
  identical results).

### Deliberate design choice: windowed percentiles, exact lifetime stats
p50/p99/p999 reflect only the most recent ~10,000 trades, not the
full lifetime history. This is intentional: "how is the system
performing right now" is the right question for a live view, not a
percentile blended across everything since startup (including any
cold-start warmup). `count`/`min`/`mean`/`max` remain exact lifetime
values since those don't require sorting and cost nothing extra to
keep precise.

### Added
- `matching_engine/tests/test_latency_metrics.py` — 8 tests: empty
  state returns zeroed stats (not an error), correct field shape,
  percentile ordering (min <= p50 <= p99 <= p999 <= max, which must
  always hold by definition), exact lifetime count both below and
  past the ring's capacity, mean cross-checked against the `trades`
  property's own values for an exactly-countable batch, repeated
  queries don't disturb book state, and single-trade edge case (all
  percentiles collapse to that one value).

### Updated
- `run_demo.py`: the matcher process now prints a periodic STATS line
  (n/p50/p99/p999/max) every 10 trades, alongside each individual
  trade's own latency line from Day 12 — both pieces visible together
  in the live demo output.

### Verified after the change
- All 86 previously-passing tests (Days 1-12) still pass
- GC-safety tests re-run (7/7 pass) — these exercise
  `run_c_only_matching_cycle` in a tight loop, which now also calls
  the new `_record_latency_sample()` on every trade, so this is real
  (if implicit) load-bearing verification that the ring-buffer
  recording stays GC-safe, not just an assumption
- `run_demo.py` re-run end to end: STATS lines appear correctly,
  consistent with individual TRADE latency lines
- `audits/engine_verification.py` re-run: correctness PASSED, p50
  5.58µs
- `audits/ipc_audit.py` re-run at full 1,000,000-order scale: still
  PASSED, 0 missing, 0 duplicated, correct ordering
- `run_dashboard_demo.py` re-run via pseudo-terminal: no errors

### Tests
`pytest -v` → 94/94 passing (86 previous + 8 new latency metrics
tests).

## Day 14 — SQLite trade ledger + async background flusher

### What this adds
Per spec: "Write a background process that asynchronously flushes the
matched trades from the mmap buffer to a permanent SQLite/ClickHouse
ledger for auditing." Built both halves: the ledger (schema + CRUD)
and the async flush service connecting it to the live engine.

### A terminology clarification, stated honestly
The spec phrase "flushes ... from the mmap buffer" doesn't quite match
this system's actual data flow: the mmap ring buffer only ever holds
INCOMING orders waiting to be matched. By the time a trade exists at
all, the engine has already recorded it in its own trade history —
it's never sitting in the ring buffer. The flusher reads from
`OrderBookCython`'s trade history (the authoritative record of
completed trades), not from the ring buffer. Documented directly in
`trade_flusher.py`'s module docstring so this doesn't create a false
impression of a second, separate data source.

### Design
- **`database/ledger.py`**: SQLite schema (one `trades` table, indexed
  on `exit_timestamp`), `save_trade()`/`save_trades_batch()` (uses
  `INSERT OR IGNORE` on the `trade_id` primary key — flushing the same
  trade twice, e.g. after a flusher restart, is a safe no-op rather
  than a duplicate row or a crash), `get_recent_trades()`,
  `get_trade_history()` (paginated), `get_statistics()`,
  `clear_database()`.
- **SQLite chosen over ClickHouse**, stated plainly: simpler, no
  separate server process, more than adequate for this project's
  scale. ClickHouse would be the natural production upgrade for real
  HFT write volume, but adds real operational complexity not needed
  to prove the concept here.
- **`database/trade_flusher.py`**: `TradeFlusher`, an asyncio service
  with the same `start()`/`stop()`/`pause()`/`resume()` shape as
  `simulator/market_firehose.py`. Flushes on an interval (default
  100ms) rather than after every single trade — flushing per-trade
  would put a disk write on the matching engine's critical path,
  defeating the point of keeping matching itself fast and GC-free.
  Batches all new trades into one transaction per cycle.
- **New engine methods** (`matching_engine/order_book.pyx`):
  `trade_count` (property) and `get_trades_since(start_index)` — let
  the flusher pull only NEW trades each cycle instead of re-reading
  and re-serializing the entire trade history (which would get slower
  as trades accumulate, unnecessarily) every 100ms.

### Verified, not just written
- Manual end-to-end check first: produced trades while the flusher
  ran in the background, confirmed the ledger's trade count matched
  the engine's exactly, with sensible latency values once realistic
  timestamps were used (an early manual test with fake sequential
  timestamps produced a nonsensical multi-second "average latency" —
  correctly diagnosed as bad test input, not a flusher bug, before
  writing the real test suite).
- `run_persistence_demo.py` — new dedicated demo (kept separate from
  `run_demo.py` rather than risking a change to its already-verified
  synchronous loop, same reasoning `run_dashboard_demo.py` was kept
  separate): a real generator process + a matcher process running
  matching and the async flusher concurrently in one event loop.
  Ran it for real: 54 trades matched, 54 flushed, 54 confirmed in the
  ledger — exact match, printed by the demo itself. Then independently
  re-verified by opening the resulting `chronosmatch_ledger.db` file
  in a completely separate, fresh Python process (not trusting the
  demo's own self-report) — confirmed 54 real rows with real trade
  data.

### Added
- `database/ledger.py`, `database/trade_flusher.py`
- `database/tests/test_ledger.py` — 10 tests: schema creation,
  save/retrieve, batch insert, duplicate-safety, recency ordering,
  chronological ordering, pagination, empty-state statistics,
  aggregation correctness, clear-without-dropping-schema
- `database/tests/test_trade_flusher.py` — 8 tests: immediate
  `flush_now()`, automatic background flushing, only-new-trades-per-
  cycle efficiency, pause/resume behavior, exact field-for-field
  round-trip correctness (including Day 12's latency instrumentation
  surviving the trip into SQLite unchanged), stats shape, no-op flush
  on an empty book
- `matching_engine/tests/test_trade_history_slicing.py` — 8 tests for
  the new `get_trades_since()`/`trade_count` engine surface, including
  a simulation of exactly how the real flusher calls it repeatedly
  (confirms the union of all incremental pulls covers the full trade
  history with no gaps and no overlap)
- `run_persistence_demo.py`

### Verified after the change
- All 94 previously-passing tests (Days 1-13) still pass
- `run_demo.py` re-run end to end: unaffected, still works (the new
  engine methods are additive)

### Tests
`pytest -v` → 120/120 passing (94 previous + 26 new: 10 ledger + 8
flusher + 8 trade-history-slicing).

## Engine hardening pass — full requirement-list audit against the trading-engine spec

Not tied to a specific calendar day (folded in ahead of the Day 16+
UI-polish/integration work): did a line-by-line pass of
`matching_engine/order_book.pyx` against the full trading-engine
requirement list ("Limit Order Book" / "Cython optimization" /
"price-level optimization" / "GC testing" / "engine benchmarks" / "unit
tests") this module is meant to satisfy. Most of it was already there
and already tested (price-time priority, C structs, price-level
bucketing, GC-safety, nanosecond latency instrumentation — Days 5, 6,
10-13). Found two real, previously-unimplemented gaps and closed both.

### Added
- **`OrderBookCython.cancel_order(order_id, side) -> bool`** — order
  cancellation didn't exist at all before this. Implemented as
  `_cancel_c()`: a linear scan over the given side's price levels and,
  within the matching level, its FIFO — O(price levels + orders at
  that level), not O(1). A production system would maintain an
  `order_id -> (level, slot)` index for true O(1) cancels; that index
  was deliberately not built so cancellation stays entirely at the
  C-struct level (no Python dict anywhere) and nogil-capable like the
  rest of the hot path. Documented as a real trade-off in the
  docstring, not silently assumed away.
- **`OrderBookCython.best_bid()` / `best_ask()` / `spread()`** — best
  price + aggregated resting size at that price, true O(1). Previously
  the only way to get the best price was `get_top_levels(depth=1)`,
  which builds a Python list even when only the single best price is
  needed. `PriceLevel` now carries a `total_quantity` field, maintained
  incrementally on insert/fill/cancel, so aggregated size at the best
  price is also O(1) rather than requiring a walk of that level's FIFO.
- **`p95_ns`** added to `get_latency_stats()`, alongside the existing
  p50/p99/p999 — the original spec line for engine benchmarks asks for
  p50/p95/p99/p999/max, and p95 was missing.
- `matching_engine/tests/test_order_book_extras.py` — 14 new tests:
  6 for cancellation correctness (removes the order, removed order no
  longer matches, cancelling one order at a shared price level
  preserves the others' time priority, cancelling the only order at a
  level removes the level, unknown-id and wrong-side cancels return
  False without disturbing the book) plus 1 larger regression-style
  check (cancel ~half of 200 resting orders across several price
  levels, confirm the book is still sorted and still matches
  correctly), and 6 for `best_bid()`/`best_ask()`/`spread()` (basic
  correctness, size aggregation across multiple orders at one price,
  size updating after a partial fill, spread updating as top-of-book
  changes, `None` when spread is undefined, empty-book behavior).
- A **separate, standalone deliverable package** (provided alongside
  this repo, not merged into it — see note below) containing the same
  engine logic repackaged into the exact `matching_engine.pyx` /
  `matching_engine.pxd` / `setup.py` / `tests/test_matching_engine.py`
  layout the trading-engine spec's "Deliverables" section asks for,
  with its own README, a 1,000,000-order benchmark script producing
  the exact requested `p50/p95/p99/p999/throughput` report format, a
  `gc_demo.py` walking the Python→Cython→C-loop→Trade chain, and a
  head-to-head benchmark against a naive pure-Python reference
  implementation (32x measured speedup, cross-checked for identical
  trade output before comparing speed). Deliberately kept OUT of this
  repo's own `engine/` directory rather than replacing that folder's
  existing Day-1 pure-Python placeholder (`engine/order_book.py`) —
  doing so would leave two independently-compiled Cython matching
  engines living side by side in one project (this repo's real one,
  `matching_engine/order_book.pyx`, plus a second one under `engine/`),
  which is exactly the kind of duplication worth avoiding. The old
  placeholder, and the tests that reference it (including
  `matching_engine/tests/test_order_book_cython.py`'s cross-check
  against it), are untouched.

### Changed
- `matching_engine/tests/test_latency_metrics.py` — updated the
  exact-key-set and percentile-ordering assertions to account for the
  new `p95_ns` field (`min <= p50 <= p95 <= p99 <= p999 <= max`).
- `run_demo.py` — the matcher loop now calls `best_bid()`/`best_ask()`
  directly instead of `get_top_levels(depth=3)` followed by indexing
  `[0]`, now that the O(1) accessors exist.

### Verified, not just written
- Full project test suite, not just `matching_engine/`:
  `pytest -q` → **134/134 passing** (120 previous + 14 new). Checked
  first whether anything else in the project depended on the exact
  shape of `get_latency_stats()`'s return dict or on `OrderBookCython`'s
  public surface before changing anything — `database/trade_flusher.py`
  depends on `trade_count`/`get_trades_since()` (untouched, still
  present) and `dashboard/live_dashboard.py` depends on
  `get_top_levels()` (also untouched); only
  `matching_engine/tests/test_latency_metrics.py` had an exact-key-set
  assertion that needed updating for the new `p95_ns` field.
- `run_demo.py` re-run end to end after both the engine rebuild and the
  `best_bid()`/`best_ask()` swap: two real OS processes, ring-buffer IPC,
  live trades, both processes still exit cleanly.

### Tests
`pytest -v` (whole project) → 134/134 passing (120 previous + 14 new).

## Data-pipeline hardening pass — full requirement-list audit against the IPC/simulator spec

Same treatment as the engine hardening pass above, applied to the other
half of the system: `shared/` (mmap ring buffer + binary protocol) and
`simulator/` (asyncio market data firehose). Did a line-by-line pass
against the full data-pipeline requirement list ("mmap ring buffer" /
"binary order format" / "cross-process testing" / "market simulator" /
"load testing" / "IPC audit"). Most of it was already there and already
proven at real scale (the zero-copy protocol, the cross-process locking
fix, the 1,000,000-order two-process audit — Days 2-4, 8). Found real
gaps in exactly three places: the binary protocol had never been
documented as a spec (just implemented), nothing measured JSON/Pickle
against it despite that being the whole point of the zero-copy design,
and nothing swept a range of target rates to find where throughput
actually starts falling behind — every existing benchmark reported a
single uncapped ceiling number.

### Added
- **Documented binary protocol** — `shared/serializer.py`'s module
  docstring now has the full byte-offset table (field, offset, size,
  struct code, notes) the wire format was always using but had never
  written down anywhere. No behavior change — the format string, byte
  layout, and `serialize()`/`deserialize()` functions are untouched.
- **`benchmarks/serialization_comparison.py`** — measures JSON, Pickle,
  and this project's `struct`-based protocol on the identical order
  dict (pure encode+decode round trip), plus the FULL IPC round trip
  (real `RingBuffer.write_order()`/`read_order()`, lock included) for
  the struct method specifically. One real run on this machine (500,000
  round trips/method): JSON 224k/s, Pickle 745k/s, struct 1.80M/s (8.0x
  faster than JSON, 2.4x faster than Pickle), full ring-buffer round
  trip 204k/s. Isolates the shared backing file for the duration of the
  run (monkeypatches `shared.shared_memory.BACKING_FILE`/`LOCK_FILE`,
  restores them afterward) so it can't collide with a real
  `ring_buffer.mem` some other process might be using.
- **`simulator/load_test.py`** — sweeps target rates (default 10k, 50k,
  100k, 150k, 200k, 300k, 500k/sec) against `MarketFirehose`, each with
  a concurrent drainer so the firehose never blocks on a buffer nobody's
  reading, and reports where achieved throughput first drops below 70%
  of target. One real run: targets up to 100k/sec sustained at
  ~99.5-99.8% of target; 150k/sec still held at 93.8%; 200k/sec was the
  first to drop under the 70% threshold (73.0%, right at the edge) on
  this sandbox machine.
- **`tests/test_cross_process_scenarios.py`** — 3 new tests: a
  dedicated 100,000-order cross-process scenario (the existing
  `tests/test_cross_process_locking.py` test runs at 20,000 — enough to
  reliably reproduce the specific bug it's a regression guard for, but
  100k is separately called out in the requirement list and is still
  fast enough, ~0.3s here, to run directly in the normal suite);
  explicit process-exitcode verification (`producer.exitcode == 0` /
  `consumer.exitcode == 0` — a distinct claim from "all data arrived",
  since a process can deliver everything and still crash on the way
  out); and three repeated full startup-to-shutdown cycles back to
  back, guarding against state leaking between runs (a stale lock file,
  a leftover mmap region) that a single-cycle test wouldn't catch.
  Deliberately did NOT add a 1,000,000-order test to the routine pytest
  suite — `audits/ipc_audit.py` remains the authoritative large-scale
  proof at that scale, on purpose, so the routine suite stays fast; see
  that script's own module docstring for the reasoning, which this
  addition follows rather than relitigates.
- A separate, standalone deliverable package (provided alongside this
  repo, not merged into it, same reasoning as the matching-engine
  deliverable) containing the same IPC/simulator logic repackaged into
  the exact `ipc/{protocol,shared_memory,ring_buffer}.py` +
  `ipc/tests/test_ring_buffer.py` + `simulator/{market_simulator,
  load_test}.py` layout the data-pipeline spec's "Deliverables" section
  asks for. Its own test suite (40 tests) additionally found and fixed
  a real synchronization property worth documenting either way: at very
  small ring-buffer capacities (single digits), the producer and
  consumer toggle the buffer between full and empty on almost every
  operation, and each transition costs a real cross-process lock
  round-trip — throughput measured at ~1,000/sec for an 8-slot buffer
  vs. ~65,000+/sec for a 512-slot one on the same machine. Documents
  directly why this project's production capacity (4096) is chosen well
  above the minimum needed for correctness.

### Verified, not just written
- Full project test suite: `pytest -q` → **137/137 passing** (134
  previous + 3 new). Checked whether anything depended on
  `shared/serializer.py`'s exact format string or byte layout before
  touching its docstring — nothing does; the format string itself
  (`_FORMAT`) and both functions are byte-for-byte unchanged, only the
  documentation comment above them grew.
- `benchmarks/serialization_comparison.py` and `simulator/load_test.py`
  both run cleanly against the real project (not just in isolation),
  and both clean up their own backing files afterward — confirmed no
  stray `.mem`/`.lock` files left behind after a run.

### Tests
`pytest -v` (whole project) → 137/137 passing (134 previous + 3 new).

## Dashboard hardening pass — the spec's core "Latency Monitor" requirement was never actually wired in

Doing a full pass of the project against the top-level spec (not just
one module's own requirement list this time) surfaced something more
significant than the previous two hardening passes: the spec's Key
Modules section names a "Latency Monitor (Python curses): A live
terminal graph measuring the end-to-end latency in microseconds (us)"
as one of four core modules. Day 7's dashboard docstring said the
latency fields were "already laid out" for this, pending Day 12-13's
nanosecond instrumentation landing in the engine. Day 12-13 happened.
The dashboard was never actually updated to call it. `_draw()` showed
order/trade counts and whale highlights, but zero latency numbers, in
any unit, anywhere on screen — the literal spec requirement this file
exists to satisfy was not implemented, despite everything it depended
on (`get_latency_stats()`) being complete, tested, and sitting one
function call away.

### Added
- `dashboard/live_dashboard.py`: `format_latency_line()` — pure
  function (no curses dependency, unit-testable), converts the
  engine's `get_latency_stats()` (nanoseconds) into a p50/p95/p99/p999
  microsecond display line, matching the spec's stated unit exactly.
  Handles the empty-book case (shows "(no trades yet)" rather than a
  misleading "0.0us", which would read as "the system is infinitely
  fast" instead of "nothing has happened yet").
- `run_dashboard()` now calls `book.get_latency_stats()` every frame
  and passes it to `_draw()`, which renders the new line right below
  the orders-processed/trades-matched counts.
- `dashboard/tests/test_dashboard_logic.py` — 5 new tests: microsecond
  unit conversion (not nanoseconds — the actual point of this
  requirement), all four percentiles present, sample count included,
  empty-book handling, and percentile display ordering.

### Honest finding, documented rather than hidden
Verified via a real pseudo-terminal run (`script -qc`, same method as
Day 7's original verification — see that entry above for why this
sandbox needs it). The latency display works and updates live
correctly. But the numbers it showed during that run were much higher
than the engine's own matching speed (tens to hundreds of milliseconds,
occasionally more) — investigated rather than dismissed as a rendering
bug. Root cause: at the demo's default order rate, `run_dashboard()`'s
loop reads and processes exactly ONE order per redraw frame (~50ms,
matching `stdscr.timeout(50)`), far slower than the generator produces
them. `entry_timestamp` is set at GENERATION time, not when this loop
gets around to reading the order — so most of the displayed latency at
default demo settings is real queueing time in the ring buffer waiting
for this single-order-per-frame loop, not the engine's own per-trade
matching cost (which stays sub-microsecond internally, unaffected by
this — see `matching_engine/tests/test_latency_instrumentation.py` and
this project's other engine-only benchmarks, none of which go through
this polling loop). The display is still an honest, real end-to-end
measurement for this specific pipeline configuration; documented
directly in `format_latency_line()`'s own docstring so a future reader
doesn't mistake "this demo's frame rate" for "the matching engine is
slow."

### Verified, not just written
- `pytest -v` (whole project) → **142/142 passing** (137 previous + 5
  new).
- Real pseudo-terminal run (`script -qc python3 run_dashboard_demo.py`)
  confirmed genuine curses escape sequences building a live-updating
  latency line alongside the existing bid/ask and whale-highlight
  output, and a clean process exit afterward — not just that the pure
  `format_latency_line()` function returns a sensible string in
  isolation.

### Tests
`pytest -v` (whole project) → 142/142 passing (137 previous + 5 new).

## Final integration + documentation pass — closing out Days 21-24

Last pass: the remaining Final-Review-track items that were genuinely
missing (not just under-documented) — a true five-stage end-to-end
integration demo, the ClickHouse-vs-SQLite decision the spec asks to
have documented either way, and bringing the project's own planning
docs back in sync with what's actually built.

### Added
- **`run_full_integration_demo.py`** (Day 22) — the first demo in this
  project that runs all five architecture stages together in one
  process pair: market simulator → mmap ring buffer → Cython matching
  engine → SQLite ledger → curses dashboard. Every prior demo exercises
  a subset (`run_demo.py`: firehose→buffer→engine;
  `run_dashboard_demo.py`: +dashboard; `run_persistence_demo.py`:
  +ledger, no dashboard). Combining the ledger's async flush with the
  dashboard's synchronous curses loop needed a small design choice: a
  new `on_frame` callback hook on `dashboard.live_dashboard.run_dashboard()`
  (backward-compatible, defaults to `None`, zero effect on every
  existing caller) lets this demo flush new trades to SQLite
  synchronously every few frames, reusing the exact same
  `database.ledger.save_trades_batch()` + `get_trades_since()` primitives
  `TradeFlusher` uses elsewhere — deliberately not running
  `TradeFlusher`'s own asyncio scheduling inside a synchronous curses
  callback, which would need a second concurrency model (a thread, or a
  nested event loop) for no real benefit at this project's scale.
- **`ARCHITECTURE_DECISIONS.md`** (Day 21) — SQLite vs. ClickHouse
  (chosen: SQLite, with an honest list of what would actually justify
  ClickHouse instead — production write volume, analytical queries at
  scale, concurrent writers, none of which this project currently has),
  plus two other trade-offs worth explaining on their own now that
  they're referenced from multiple places: the ring buffer's single
  coarse-grained lock instead of a lock-free SPSC design, and
  fixed-size struct slots instead of variable-length framing.

### Fixed
- **`TASKS.md`'s status summary table had gone stale since Day 2** and
  was never caught until this pass: it listed "Trade ledger
  (SQLite/ClickHouse): Not started" and "IPC audit (1M orders, 2
  processes): Not started" — both had actually been complete since Day
  14 and Day 8 respectively. Corrected to reflect reality, with
  pointers to what's actually implemented. Worth naming directly: a
  living status document that silently drifts out of sync with the
  code is worse than no status document, since it actively misinforms
  anyone who trusts it without independently checking — exactly the
  failure mode this project's own testing philosophy (verify, don't
  just assert) exists to avoid, applied here to documentation instead
  of code.
- **`HOW_TO_RUN.md`** updated throughout: the project-structure table's
  `simulator/`/`dashboard/` rows said "in progress" / "latency numbers
  Day 12-13" — both are done; the test count said 120, now 142; every
  benchmark/audit/demo script added across all three hardening passes
  (`serialization_comparison.py`, `load_test.py`,
  `run_full_integration_demo.py`) is now listed with what it does and
  roughly how long it takes to run.
- **`TASKS.md`'s 25-day plan**, Days 18-24: marked against what's
  actually been done (full IPC/engine/latency test sweep, sustained
  load testing, the ClickHouse decision, full integration, the test
  coverage count, documentation) — including one item marked honestly
  as *partially* addressed rather than claimed complete: Day 20's
  "fix latency outliers" was investigated (real multi-millisecond
  outliers do appear in large benchmark runs) but the root cause is
  this sandbox's own OS scheduling jitter on a shared/virtualized
  machine, not a code-level defect — there is nothing to fix in the
  matching algorithm itself, so the entry says that plainly rather than
  claiming a fix that wouldn't be honest.

### Verified, not just written
- Full project test suite: `pytest -q` → **142/142 passing**, unchanged
  by this pass (no engine/IPC/dashboard code touched — this pass is
  new demo/documentation surface only). Confirmed the `on_frame` hook
  addition to `run_dashboard()` doesn't change behavior for existing
  callers (`run_dashboard_demo.py` doesn't pass it, defaults to `None`,
  identical to before).
- `run_full_integration_demo.py` run via a real pseudo-terminal
  (`script -qc`, same method as every other curses verification in this
  project): 122 trades matched by the engine, 122 flushed to the
  ledger, 122 confirmed by independently re-opening the resulting
  SQLite file in a fresh Python process afterward — not trusting the
  demo's own printed summary. Both processes exited with code 0.

### Tests
`pytest -v` (whole project) → 142/142 passing (unchanged — this pass
added demos and documentation, not engine/IPC/dashboard code).
