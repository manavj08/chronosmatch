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
| `matching_engine/` — Cython engine | `.pyx`, C-structs/C-types, no GIL/GC in hot path | In progress — real matching logic done (Day 5), GC/object-stripping optimization pass Day 6 |
| `simulator/` — asyncio firehose | asyncio, 100,000 orders/sec target | Done for this phase — hits ~100k/sec target on single-core sandbox (see Day 4 benchmark). Real websocket data source not in scope; noted honestly in Day 3 entry. |
| `dashboard/` — curses latency UI | Terminal UI, live Bid/Ask, μs latency | Not started |
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
| 6 | 2 | Strip remaining Python object interaction from the matching loop; confirm no GC triggers during a match |
| 7 | 2 | curses terminal dashboard — live Bid/Ask top-of-book display |
| 8 | 2 | Mid-Project Review: IPC audit — 1M orders between two real OS processes, no Pickle, prove zero-copy holds under load |
| 9 | 2 | Mid-Project Review: Engine verification — automated proof a Buy instantly matches a corresponding Sell |
| 10 | 3 | C-level optimization pass on the matching loop |
| 11 | 3 | GC-pause verification: instrument gc stats, prove zero collections trigger during a trade |
| 12 | 3 | Embed `time.perf_counter_ns()` entry/exit timestamps per order |
| 13 | 3 | Latency metrics pipeline — nanosecond precision end-to-end, p50/p99/p999 |
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
