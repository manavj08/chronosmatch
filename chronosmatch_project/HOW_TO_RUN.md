# How to Run — ChronosMatch

Windows, Command Prompt or PowerShell. You'll also need a C compiler
for the Cython build step (Visual Studio Build Tools on Windows —
"Desktop development with C++" workload; already required per the
company spec).

## 1. Setup

```
cd chronosmatch_project
python -m venv venv
venv\Scripts\activate      # Windows (PowerShell / Command Prompt)
# source venv/bin/activate # Linux / macOS
pip install -r requirements.txt
```

## 2. Build the Cython matching engine

The matching engine is a compiled C-extension, not plain Python — it
must be built before it can be imported or tested.

```
python setup_demo.py
```

(This is the same as running `cd matching_engine && python setup.py
build_ext --inplace`, just from the project root for convenience.)

This produces a platform-specific `order_book.pyd` (Windows) or
`order_book.so` (Linux/macOS) inside `matching_engine/`. It is not
committed to git — rebuild it after every fresh clone or pull.

## 3. Run the live demo

```
python run_demo.py
```

This starts two REAL, separate operating system processes:
- a **generator** process that creates random buy/sell orders and
  writes them into the shared-memory ring buffer
- a **matcher** process that reads from the SAME memory region and
  feeds every order into the compiled Cython order book

Runs for 10 seconds by default (5 orders/sec, deliberately slow so
it's easy to watch and narrate). You'll see both processes' PIDs in
the output — proof they're genuinely separate processes, not two
threads — the best bid/ask updating live as orders land, and TRADE
lines whenever an incoming order actually crosses and matches against
the book (Day 5).

**What this demo proves:** zero-copy IPC between two real processes,
the compiled Cython engine actually running, and real price-time
priority matching — trades executing live, including partial fills
across multiple resting orders.
**Scope note:** this specific demo is deliberately plain-text and
synchronous, at a small, readable order rate, so it's easy to watch
and narrate live — the curses dashboard (with live microsecond latency
numbers), the async SQLite ledger, and a full five-stage integration
are separate demos (sections 5b, 5c, 5d below) rather than crammed into
this one. Day 4's asyncio firehose can sustain ~100k/sec (see
`benchmarks/`, `simulator/load_test.py`), well above what this demo's
default rate uses on purpose.

Adjust `DEMO_DURATION_SECONDS` / `ORDERS_PER_SECOND` at the top of
`run_demo.py` if you want it faster, slower, or longer for a
presentation.

## 4. Verify the project works

```
pytest -v
```

147 tests should currently pass. `matching_engine/tests/` will skip
with a clear message (not fail) if you haven't run the build step
above yet.

## 5. Run each piece independently

```
python -m engine.order_book               # pure-Python reference engine, real ring buffer
python -m shared.ring_buffer               # (importable only, no __main__ demo yet)
python -m simulator.order_generator        # order generation smoke test (still used internally by market_firehose.py)
python -m simulator.market_firehose        # asyncio firehose smoke test (Day 3), ~3s at 50 orders/sec
python benchmarks/throughput_benchmark.py  # Day 4: layer-by-layer throughput measurement, ~10s
python audits/ipc_audit.py                 # Day 8: 1,000,000-order Mid-Project Review IPC audit, ~8-30s depending on hardware
python audits/engine_verification.py       # Day 9: Buy/Sell matching verification + latency report, ~1-2s
python benchmarks/level_bucketing_benchmark.py  # Day 10: price-level bucketing benchmark (realistic vs adversarial), ~1s
python benchmarks/serialization_comparison.py   # JSON vs Pickle vs struct throughput comparison, ~5-10s
python simulator/load_test.py                   # graduated rate sweep (10k...500k/sec), finds where throughput breaks down, ~15s
```

`simulator_starter.py` (repo root) is leftover from the very first
skeleton, before the company spec was issued — it's a broken import
and will be removed once the real `simulator/` (asyncio) package
fully replaces its role. `dashboard_starter.py` has already been
removed (Day 7) — its role is now `dashboard/live_dashboard.py`, a
real implementation, not a placeholder.

## 5b. Run the live terminal dashboard

```
python run_dashboard_demo.py
```

Starts a generator process + the real terminal dashboard, both reading
from/writing to the shared-memory ring buffer. Shows a live Bid/Ask
order book, running totals, live p50/p95/p99/p999 latency in
microseconds (sourced directly from the engine's own
`get_latency_stats()`), and highlights any trade at or above 50 units
of quantity as a "whale" trade. Runs 20 seconds by default, or press
Ctrl+C to exit early.

**Display Modes & Terminal Compatibility:**
The dashboard automatically detects your environment:
- **Interactive Console** (Windows Command Prompt, native PowerShell): runs via `curses` (`windows-curses`).
- **IDE Terminals (VS Code, etc.) / Piped / Redirected Shells:** automatically falls back to an in-place ANSI terminal renderer to prevent PDCurses "Redirection is not supported" errors.

You can also explicitly select the display mode, duration, or order rate via CLI flags:
```
python run_dashboard_demo.py --mode ansi              # force ANSI text mode
python run_dashboard_demo.py --mode curses            # force curses mode
python run_dashboard_demo.py --duration 30 --rate 10  # customize duration & order rate
```

**Reading the latency numbers:** at this demo's default (small,
readable) order rate, the dashboard's render loop reads one order per
~50ms frame — slower than orders are generated — so most of the
displayed latency reflects real queueing time waiting for that
single-order-per-frame loop, not the matching engine's own per-trade
speed (which stays sub-microsecond internally regardless of this demo's
frame rate — see `matching_engine/tests/test_latency_instrumentation.py`
and this project's engine-only benchmarks for that number measured
without a display loop in the way). See
`dashboard/live_dashboard.py`'s `format_latency_line()` docstring for
the full explanation.

## 5c. Run the persistence (SQLite ledger) demo

```
python run_persistence_demo.py
```

Real generator process + a matcher process that both matches orders
and runs the async trade flusher concurrently. Produces a real SQLite
file, `chronosmatch_ledger.db`, in the project root. At the end, the
demo prints the engine's trade count and the ledger's trade count and
confirms they match. Inspect the file yourself afterward:

```
python -c "import sqlite3; c = sqlite3.connect('chronosmatch_ledger.db'); print(c.execute('SELECT * FROM trades LIMIT 10').fetchall())"
```

(or use any SQLite browser/CLI tool you have installed).

## 5d. Run the full end-to-end integration demo

```
python run_full_integration_demo.py
```

The one demo that puts every stage of the architecture in a single
run: market simulator → mmap ring buffer → Cython matching engine →
SQLite ledger → curses dashboard, all together. Every other demo above
exercises a subset of this chain; this is the Day 22 "does the whole
thing actually work end to end, not just pairwise" proof. Runs 20
seconds by default. At the end (after the curses screen closes), it
prints how many trades were flushed to the ledger and the ledger's own
trade count, so you can see the two agree without trusting the demo's
own self-report — cross-check it yourself the same way section 5c
describes.

## 6. Project structure

| Folder | Purpose | Spec module |
|---|---|---|
| `shared/` | mmap ring buffer, zero-copy IPC (binary protocol documented in `shared/serializer.py`) | Zero-Copy IPC Bus |
| `matching_engine/` | Cython Limit Order Book (price-time priority, cancellation, O(1) best bid/ask/spread) | Cython Matching Engine |
| `engine/` | Pure-Python reference implementation, used to verify the Cython version's correctness | — |
| `simulator/` | Order generation (asyncio firehose, ~100k/sec sustained; `load_test.py` finds the actual breakdown point) | Market Simulator |
| `dashboard/` | curses terminal latency UI — live Bid/Ask, whale highlights (Day 7), live p50/p95/p99/p999 microsecond latency | Latency Monitor |
| `database/` | SQLite trade ledger + async flusher (Day 14) | Resiliency, Week 4 |
| `audits/` | Cross-process IPC audit (1M orders) + engine verification | Mid-Project Review |
| `benchmarks/` | Throughput, price-level bucketing, and serialization-method (JSON/Pickle/struct) comparisons | — |
| `archive_web_dashboard/` | Earlier self-directed plan (FastAPI + web UI), kept for reference, not part of the active deliverable | — |

A separate, spec-exact `engine/matching_engine.pyx`+`.pxd` package and
an `ipc/`+`simulator/` package are also provided alongside this repo
(not merged into it, to avoid duplicating the real modules above under
a second name) — see `ARCHITECTURE_DECISIONS.md` and each package's own
README for why, and CHANGELOG.md's hardening-pass entries for what each
one closed.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: order_book` (in `matching_engine/tests/`) | Extension not built yet — run the build step in section 2 |
| Cython build fails with a compiler error | Confirm a C compiler is installed and on PATH (`gcc --version` or, on Windows, the VS Build Tools C++ workload) |
| `ModuleNotFoundError: curses` | Run `pip install windows-curses` (already in requirements.txt for Windows) |
| `Redirection is not supported.` or curses crash | The dashboard automatically falls back to ANSI mode; you can also force it via `--mode ansi` (e.g. `python run_dashboard_demo.py --mode ansi`), or run in a native console window |
| `ImportError` on `shared_interface` | That module was removed early on — use `shared.ring_buffer.RingBuffer` instead |
| Dashboard renders garbled/errors | Enlarge the terminal window, or run in ANSI mode with `--mode ansi` |
| Tests fail after a change | Run `pytest -v` for the specific failing file first; check `CHANGELOG.md` for what changed that day |
