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
threads — and the best bid/ask updating live as orders land.

**What this demo proves:** zero-copy IPC between two real processes,
and the compiled Cython engine actually running.
**What it doesn't show yet** (honestly, not built yet — see
`TASKS.md`): real trade matching/crossing, the curses dashboard,
microsecond latency numbers, and the full 100k-orders/sec asyncio
firehose. The demo uses a small, readable rate on purpose.

Adjust `DEMO_DURATION_SECONDS` / `ORDERS_PER_SECOND` at the top of
`run_demo.py` if you want it faster, slower, or longer for a
presentation.

## 4. Verify the project works

```
pytest -v
```

28 tests should currently pass. `matching_engine/tests/` will skip
with a clear message (not fail) if you haven't run the build step
above yet.

## 5. Run each piece independently

```
python -m engine.order_book               # pure-Python reference engine, real ring buffer
python -m shared.ring_buffer               # (importable only, no __main__ demo yet)
python -m simulator.order_generator        # order generation smoke test (still used internally by market_firehose.py)
python -m simulator.market_firehose        # asyncio firehose smoke test (Day 3), ~3s at 50 orders/sec
python benchmarks/throughput_benchmark.py  # Day 4: layer-by-layer throughput measurement, ~10s
```

`simulator_starter.py` and `dashboard_starter.py` (repo root) are
leftover from the very first skeleton, before the company spec was
issued — both are broken imports and will be removed once the real
`simulator/` (asyncio) and `dashboard/` (curses) packages replace them.

## 6. Project structure

| Folder | Purpose | Spec module |
|---|---|---|
| `shared/` | mmap ring buffer, zero-copy IPC | Zero-Copy IPC Bus |
| `matching_engine/` | Cython Limit Order Book | Cython Matching Engine |
| `engine/` | Pure-Python reference implementation, used to verify the Cython version's correctness | — |
| `simulator/` | Order generation (asyncio firehose, in progress) | Market Simulator |
| `dashboard/` | curses terminal latency UI (not started) | Latency Monitor |
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
