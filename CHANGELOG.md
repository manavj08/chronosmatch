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
