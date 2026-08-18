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
| `shared/` — mmap ring buffer | Zero-copy, raw `struct`, no pickle | Done — confirmed spec-compliant as built, no changes needed |
| `matching_engine/` — Cython engine | `.pyx`, C-structs/C-types, no GIL/GC in hot path | Done for this phase — matching logic (Day 5) + GC-free C-array storage (Day 6) both verified with tests. Further C-level optimization pass Day 10. |
| `simulator/` — asyncio firehose | asyncio, 100,000 orders/sec target | Done for this phase — hits ~100k/sec target on single-core sandbox (see Day 4 benchmark). Real websocket data source not in scope; noted honestly in Day 3 entry. |
| `dashboard/` — curses latency UI | Terminal UI, live Bid/Ask, μs latency | In progress — live Bid/Ask + whale highlighting done (Day 7), μs latency instrumentation Day 12-13 |
| Trade ledger (SQLite/ClickHouse) | Async flush from mmap buffer | Not started |
| IPC audit (1M orders, 2 processes) | Prove zero-copy, no Pickle bottleneck | Not started |

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
| 14 | 4 | Background async flush: mmap buffer -> SQLite ledger |
| 15 | 4 | SQLite ledger schema + audit trail correctness tests |
| 16 | 4 | curses UI polish — highlight "whale" orders clearing multiple price levels |
| 17 | 4 | curses UI polish continued — visual refinement, responsiveness |
| 18 | — | Final Review prep: full IPC + engine + latency test sweep |
| 19 | — | Load test: sustained firehose at target throughput under real conditions |
| 20 | — | Fix latency outliers / GC triggers found under load |
| 21 | — | ClickHouse evaluation vs SQLite — document the decision either way |
| 22 | — | End-to-end integration: firehose -> ring buffer -> Cython engine -> ledger -> dashboard |
| 23 | — | Test coverage pass across all modules |
| 24 | — | Documentation: architecture, benchmarks, build/run instructions |
| 25 | — | Final polish, Final Review deliverable |

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
