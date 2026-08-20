# How to Run — ChronosMatch

Windows, Command Prompt or PowerShell. You'll also need a C compiler
for the Cython build step (Visual Studio Build Tools on Windows —
"Desktop development with C++" workload; already required per the
company spec).

## 1. Setup

```
cd chronosmatch
python -m venv venv
venv\Scripts\activate
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
**What it doesn't show yet** (honestly, not built yet — see
`TASKS.md`): the curses dashboard, microsecond latency numbers, and
GC-pause verification during matching. The demo also uses a small,
readable order rate on purpose — Day 4's asyncio firehose can sustain
~100k/sec (see `benchmarks/`), but that would scroll by too fast to
narrate live.

Adjust `DEMO_DURATION_SECONDS` / `ORDERS_PER_SECOND` at the top of
`run_demo.py` if you want it faster, slower, or longer for a
presentation.

## 4. Verify the project works

```
pytest -v
```

120 tests should currently pass. `matching_engine/tests/` will skip
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
```

`simulator_starter.py` (repo root) is leftover from the very first
skeleton, before the company spec was issued — it's a broken import
and will be removed once the real `simulator/` (asyncio) package
fully replaces its role. `dashboard_starter.py` has already been
removed (Day 7) — its role is now `dashboard/live_dashboard.py`, a
real implementation, not a placeholder.

## 5b. Run the live curses dashboard

```
python run_dashboard_demo.py
```

Starts a generator process + the real curses dashboard, both reading
from/writing to the shared-memory ring buffer. Shows a live Bid/Ask
order book, running totals, and highlights any trade at or above 50
units of quantity as a "whale" trade. Runs 20 seconds by default, or
press Ctrl+C to exit early.

**Note:** curses needs a real terminal (TTY) to render — it will not
work if piped through something that isn't one (e.g. some CI
environments, some IDE "run" panels that don't allocate a real
terminal). If you see a `cbreak() returned ERR` error, run it directly
in Command Prompt/PowerShell/a real terminal window instead.

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

## 6. Project structure

| Folder | Purpose | Spec module |
|---|---|---|
| `shared/` | mmap ring buffer, zero-copy IPC | Zero-Copy IPC Bus |
| `matching_engine/` | Cython Limit Order Book | Cython Matching Engine |
| `engine/` | Pure-Python reference implementation, used to verify the Cython version's correctness | — |
| `simulator/` | Order generation (asyncio firehose, in progress) | Market Simulator |
| `dashboard/` | curses terminal latency UI (live Bid/Ask done Day 7; latency numbers Day 12-13) | Latency Monitor |
| `database/` | SQLite trade ledger + async flusher (Day 14) | (Resiliency, Week 4) |
| `archive_web_dashboard/` | Earlier self-directed plan (FastAPI + web UI), kept for reference, not part of the active deliverable | — |

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: order_book` (in `matching_engine/tests/`) | Extension not built yet — run the build step in section 2 |
| Cython build fails with a compiler error | Confirm a C compiler is installed and on PATH (`gcc --version` or, on Windows, the VS Build Tools C++ workload) |
| `ModuleNotFoundError: curses` | Run `pip install windows-curses` (already in requirements.txt for Windows) |
| `ImportError` on `shared_interface` | That module was removed early on — use `shared.ring_buffer.RingBuffer` instead |
| Dashboard renders garbled/errors | Enlarge the terminal window; some IDE terminals don't fully support curses — use Command Prompt/PowerShell directly |
| Tests fail after a change | Run `pytest -v` for the specific failing file first; check `CHANGELOG.md` for what changed that day |
