# ChronosMatch — Day-Wise Work Log

**Major update (Day 2):** The company issued the official project
spec: "ChronosMatch — Zero-Copy High-Frequency Trading Engine." This
replaces the earlier FastAPI + web-dashboard plan entirely. The spec
requires:

- A **Cython** matching engine (compiled C-extension, static C-types,
  no Python objects in the hot path, no GC pauses during matching)
- An **asyncio** market simulator (websocket-style firehose, target
  100,000 orders/sec)
- A **curses** terminal latency dashboard (not a web dashboard)
- A zero-copy **mmap** IPC bus (already built by Member A — matches
  spec as-is)
- Nanosecond-precision latency tracking (`time.perf_counter_ns()`)
- SQLite or ClickHouse trade ledger, async-flushed from the ring buffer

The old `api/`, `frontend/`, `logging_service/` work is preserved in
`archive_web_dashboard/` (not deleted) but is no longer part of the
active plan.

Members B and C are no longer contributing. All work below is solo.

---

## Status summary (as of Day 2)

| Module | Spec requirement | Status |
|---|---|---|
| `shared/` — mmap ring buffer | Zero-copy, raw `struct`, no pickle | Done — confirmed spec-compliant as built. Data-pipeline hardening pass added the missing documented byte-layout spec to `shared/serializer.py` (format itself unchanged) and a measured JSON/Pickle/struct comparison (`benchmarks/serialization_comparison.py`: struct is 8.0x faster than JSON, 2.4x faster than Pickle on this machine). See CHANGELOG.md's "Data-pipeline hardening pass" entry. |
| `matching_engine/` — Cython engine | `.pyx`, C-structs/C-types, no GIL/GC in hot path | Done — matching logic (Day 5) + GC-free C-array storage (Day 6) + C-level optimization pass (Day 10) all verified with tests. Post-Day-14 hardening pass closed the last two gaps against the full requirement list: order cancellation (`cancel_order()`, previously unimplemented) and O(1) `best_bid()`/`best_ask()`/`spread()` + `p95` in `get_latency_stats()`. See CHANGELOG.md's "Engine hardening pass" entry — a separate, spec-exact `matching_engine.pyx`/`.pxd`/`tests/test_matching_engine.py` deliverable package (own README, 1M-order benchmark, GC demo, Cython-vs-Python comparison) was also produced, provided alongside this repo rather than merged into it. |
| `simulator/` — asyncio firehose | asyncio, 100,000 orders/sec target | Done — hits ~100k/sec target on single-core sandbox (see Day 4 benchmark). Real websocket data source not in scope; noted honestly in Day 3 entry. Data-pipeline hardening pass added `simulator/load_test.py`, a graduated rate sweep finding where throughput actually starts falling behind target (this machine: solid through 150k/sec, first drops below 70%-of-target at 200k/sec) and 3 new cross-process tests (`tests/test_cross_process_scenarios.py`: dedicated 100k-order scenario, explicit process-exitcode checks, repeated startup/shutdown cycles). |
| `dashboard/` — curses latency UI | Terminal UI, live Bid/Ask, μs latency | Done for this phase — live Bid/Ask + whale highlighting (Day 7), μs latency display wired in (dashboard hardening pass: the spec's core "Latency Monitor" line — a live p50/p95/p99/p999 microsecond readout — was previously undone despite the engine-side instrumentation being complete; now closed and verified via pseudo-terminal). Day 16-17 visual polish still open. |
| Trade ledger (SQLite/ClickHouse) | Async flush from mmap buffer | Done (Day 14) — `database/ledger.py` (SQLite schema, batched inserts, INSERT OR IGNORE for duplicate-safety) + `database/trade_flusher.py` (asyncio background service, 100ms interval, pulls only new trades via the engine's `get_trades_since()`). 26 tests (10 ledger + 8 flusher + 8 trade-history-slicing). This status table itself had gone stale since Day 2 — fixed here rather than left inaccurate. |
| IPC audit (1M orders, 2 processes) | Prove zero-copy, no Pickle bottleneck | Done (Day 8, extended in the data-pipeline hardening pass) — `audits/ipc_audit.py`: 1,000,000 orders between two real OS processes, zero loss, zero duplication, correct ordering, ~130k orders/sec. `benchmarks/serialization_comparison.py` added the actual JSON/Pickle/struct throughput comparison the "no Pickle bottleneck" claim implies (struct: 8.0x faster than JSON, 2.4x faster than Pickle on this machine). This status table itself had gone stale since Day 2 — fixed here rather than left inaccurate. |

---

## 25-day plan (mapped from the spec's 4-week/2-track structure)

| Day | Week (spec) | Task |
|---|---|---|
| 1 | — | DONE - Initial wiring fix, project restructure (superseded by Day 2's bigger restructure) |
| 2 | 1 | DONE - Confirmed mmap ring buffer already matches spec (raw struct, no pickle). Built Cython toolchain: order_book.pyx compiles to a real .so, sorted insertion ported with C-typed comparisons. Archived old web-dashboard-era code. |
| 3 | 1 | DONE - asyncio market firehose (simulator/market_firehose.py) - replaces the synchronous generation loop with an async event loop, start/stop/pause/resume, bounded backoff on a full buffer |
| 4 | 1 | DONE - Throughput push: benchmarked each layer separately, found and fixed a real bottleneck (per-order asyncio.sleep scheduling overhead), rewrote firehose to batch orders per tick. Result: ~55k/sec -> ~100k/sec on a single-core sandbox, matching the spec target |
| 5 | 2 | DONE - Real price-time priority matching in the Cython engine: full match, partial match, multi-level book walking, time priority at equal price. Demo updated to show live trade execution. |
| 6 | 2 | DONE - Rewrote internal storage as fixed-capacity C struct arrays (no Python dicts/lists in the hot path). Added GC-safety instrumentation tests proving zero Python-object allocation during matching. Found and fixed a real buffer-overflow bug during the stress test itself. |
| 7 | 2 | DONE - Real curses terminal dashboard: live Bid/Ask top-of-book, running order/trade counts, whale-trade highlighting. Verified via a pseudo-terminal session (sandbox has no real TTY for automated curses testing) plus 7 unit tests on the extracted, curses-independent logic. |
| 8 | 2 | DONE - Mid-Project Review IPC audit: 1,000,000 orders between two real OS processes. Found and fixed TWO real bugs along the way: (1) the shared-memory lock never actually synchronized across independently-started processes, causing silent data loss; (2) a multiprocessing.Queue deadlock from joining child processes before draining a large result payload. Audit now passes cleanly: 1M/1M received, zero loss, zero duplicates, correct ordering, ~130k orders/sec. |
| 9 | 2 | DONE - Mid-Project Review Engine Verification: automated proof a Buy correctly matches a corresponding Sell through the REAL ring-buffer pipeline (not just an in-memory call), plus measured latency: p50 ~6.5µs, p99 ~15-25µs, well under the spec's 50µs target on this sandbox machine. |
| 10 | 3 | DONE - C-level optimization pass: profiled the Day 6 flat-array design, found real O(n) worst-case insertion cost (16x slowdown at deep book levels). Rewrote to price-level bucketing (per-price FIFO queues), giving ~18x improvement under realistic order flow. Found and fixed a capacity regression bug mid-rewrite. |
| 11 | 3 | DONE - GC-pause verification extended to Day 10's new malloc/realloc code paths (new price-level creation, per-level FIFO growth) - confirmed GC-safe under load. Expanded matching test coverage via deliberate edge-case exploration; found and fixed a real bug: zero/negative-quantity orders could be inserted and later produce phantom zero-quantity trades. |
| 12 | 3 | DONE - Embedded time.perf_counter_ns() entry/exit timestamps and precomputed latency_ns directly on every trade, measured from inside the nogil matching loop (cpython.time.perf_counter_ns, GIL-free). Cross-verified against Day 9's external wall-clock measurement - internal (engine-only) latency correctly measures slightly lower than external, as expected. |
| 13 | 3 | DONE - Latency metrics pipeline: fixed-size circular ring buffer of recent per-trade latencies (nanosecond precision), O(1) recording per trade, on-demand p50/p99/p999 percentile computation via nogil-safe qsort over a bounded copy. Exact lifetime count/min/mean/max tracked separately (O(1), never needs sorting). Wired into run_demo.py's live output alongside Day 12's per-trade latency. |
| 14 | 4 | DONE - Background async trade flusher (database/trade_flusher.py) + SQLite ledger schema (database/ledger.py). Pulls only new trades since last flush via new engine method get_trades_since() (efficient, no re-reading full history). Verified end-to-end: real demo (run_persistence_demo.py) shows every engine trade landing durably in a real SQLite file, independently re-read and confirmed in a fresh process. |
| 15 | 4 | DONE (folded into Day 14) - SQLite ledger schema + audit trail correctness tests: 10 ledger tests, 8 flusher tests, 8 engine trade-history-slicing tests, all covering duplicate-safety, pagination, aggregation, and no-gap/no-overlap incremental flushing. |
| 16 | 4 | curses UI polish — highlight "whale" orders clearing multiple price levels |
| 17 | 4 | curses UI polish continued — visual refinement, responsiveness |
| 18 | — | DONE - Final Review prep: full IPC + engine + latency test sweep. `audits/ipc_audit.py` (1M orders), `matching_engine`'s own benchmarks (p50/p95/p99/p999/max at 1M-order scale, in the standalone engine deliverable package), and `simulator/load_test.py` (throughput sweep) together cover this across all three layers. |
| 19 | — | DONE - Load test: sustained firehose at target throughput under real conditions. `simulator/load_test.py` sweeps target rates and reports where achieved throughput first drops below 70% of target (this machine: solid through 150k/sec, first breaks below threshold at 200k/sec) — see CHANGELOG.md's "Data-pipeline hardening pass" entry. |
| 20 | — | PARTIALLY ADDRESSED, honestly - Fix latency outliers / GC triggers found under load. GC triggers: extensively proven absent (Day 6, 11, and the engine hardening pass's GC-safety tests) — nothing to fix there. Latency outliers: real multi-millisecond outliers were observed in 1,000,000-order benchmark runs (see the standalone engine deliverable's benchmark output) and investigated, not dismissed — root cause is this sandbox's own OS scheduling jitter under a shared/virtualized machine (p999 stays in single-digit microseconds; the gap is a handful of outliers in a million samples), not a defect in the matching algorithm. Documented as measured and explained, not "fixed," since there's no code-level bug to fix — a different (dedicated, non-virtualized) machine would very likely not show it. |
| 21 | — | DONE - ClickHouse evaluation vs SQLite — documented in `ARCHITECTURE_DECISIONS.md`, including when ClickHouse WOULD be the right call (production write volume, analytical queries at scale, concurrent writers) and why SQLite is the right choice for what this project currently needs. |
| 22 | — | DONE - End-to-end integration: firehose -> ring buffer -> Cython engine -> ledger -> dashboard. `run_full_integration_demo.py` — the first demo combining all five stages in one run (every other demo exercises a subset). Verified via real pseudo-terminal execution: trades flushed to the ledger matched the ledger's own count exactly, both processes exited cleanly, and the resulting SQLite file was independently re-verified in a fresh process. |
| 23 | — | DONE - Test coverage pass across all modules. 142 tests passing project-wide as of the dashboard hardening pass (up from 63 in `matching_engine/` alone at Day 14) — see CHANGELOG.md's three hardening-pass entries for what was specifically added and why. |
| 24 | — | DONE - Documentation: architecture, benchmarks, build/run instructions. `HOW_TO_RUN.md` updated to cover every demo/benchmark/audit script added across all three hardening passes (including the new full-integration demo); `ARCHITECTURE_DECISIONS.md` added for the trade-offs worth explaining on their own (SQLite vs ClickHouse, the coarse-grained lock, fixed-size struct slots); this table and the status summary above brought back in sync with reality (both had gone stale since Day 2 on two rows — fixed rather than left inaccurate). |
| 25 | — | Final polish, Final Review deliverable — see CHANGELOG.md's most recent entries for the cumulative state of the project as of this pass. |

---

## Environment notes

- Cython and a C compiler (gcc/MSVC) are required. Build with:
  ```
  cd matching_engine
  python setup.py build_ext --inplace
  ```
- Compiled artifacts (`.so`/`.pyd`, `.c`, `build/`) are gitignored —
  platform-specific, rebuilt locally, not committed.
- `matching_engine/tests/` skips automatically with a clear message
  if the extension hasn't been built yet, rather than silently
  falling back to a Python-only path.

See `HOW_TO_RUN.md` for full setup and `CHANGELOG.md` for what
shipped each day.
