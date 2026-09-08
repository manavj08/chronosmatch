# ChronosMatch — Zero-Copy High-Frequency Trading Engine

```
chronosmatch_project/
├── matching_engine/    Cython Limit Order Book (price-time priority,
│                       cancellation, O(1) best bid/ask/spread, C structs,
│                       GC-safety proven, nanosecond latency instrumentation)
├── shared/             mmap ring buffer + documented binary protocol
├── simulator/          asyncio market firehose + graduated load-test sweep
├── dashboard/          curses live Bid/Ask + whale highlights + µs latency
├── database/           SQLite trade ledger + async background flusher
├── audits/             1,000,000-order cross-process IPC audit + engine verification
├── benchmarks/         throughput, price-level bucketing, serialization comparisons
├── engine/             plain-Python reference order book (used by the Cython
│                       engine's own test suite to verify equivalence)
├── tests/ (+ each module's own tests/)   full test suite
├── run_demo.py                    basic 2-process live demo
├── run_dashboard_demo.py          + live curses dashboard
├── run_persistence_demo.py        + SQLite ledger
├── run_full_integration_demo.py   all five stages together in one run
├── HOW_TO_RUN.md                  build/run instructions, every script explained
└── ARCHITECTURE_DECISIONS.md      design trade-offs (e.g. SQLite vs ClickHouse)
```

## Start here

```bash
cd chronosmatch_project
pip install -r requirements.txt
python setup_demo.py                # builds the Cython extension (needs a C compiler)
pytest -v                           # runs the full test suite
python run_full_integration_demo.py # see everything run together
```

Full instructions, every other demo/benchmark script, and troubleshooting
are in `chronosmatch_project/HOW_TO_RUN.md`.

## What's included

| Module | Summary |
|---|---|
| Cython Matching Engine | Price-time priority, cancellation, O(1) best bid/ask/spread, GC-safety proven under load, p50/p95/p99/p999 latency |
| Zero-Copy IPC Bus (mmap + struct) | Documented binary protocol, 1,000,000-order two-process audit (zero loss), struct measured faster than JSON and Pickle |
| Market Simulator (asyncio) | Sustained high-throughput order generation, graduated load-test sweep finds the actual throughput ceiling |
| Latency Monitor (curses) | Live Bid/Ask, whale highlighting, live p50/p95/p99/p999 microsecond latency |
| Resiliency (SQLite ledger) | Async background flusher, duplicate-safe, verified against the engine's own trade count |
| Full end-to-end integration | `run_full_integration_demo.py` runs all five stages together in one verified run |
