# ChronosMatch — Day-Wise Work Log

**Update (Day 2):** Members B and C are no longer contributing. All
remaining work (Leader + Member B's simulator/database + Member C's
frontend wiring) is being done solo, one role's task interleaved per
day across the remaining 23 days.

Everyone's code still targets the real `shared/` package (built by
Member A, already complete) — its function names/signatures are
frozen.

**Golden rule:** never rename or change the signature of
`write_order()`, `read_order()`, `get_stats()`, `is_full()`,
`is_empty()`, `size()` without checking every call site first.

---

## Status summary (as of Day 2)

| Module | Status |
|---|---|
| Ring buffer / IPC (`shared/`) | Done — real mmap, all tests pass (built pre-Day-1) |
| Matching engine (`engine/`) | In progress — wiring (Day 1) + sorted insertion (Day 2) done, matching logic Day 3+ |
| Simulator (`simulator/`) | In progress — config + order generation (Day 2) done, sim control + ring buffer wiring Day 4 |
| Database (`database/`) | Not started (Day 6) |
| FastAPI + WebSocket (`api/`) | Not started (Day 13+) |
| Web dashboard (`frontend/`) | UI built, zero live data. Test scaffold added Day 2. `api.js`/`websocket.js` wiring pending. |

---

## 25-day plan (all roles, solo)

| Day | Task |
|---|---|
| 1 | DONE - Leader: fix wiring bug, resolve naming collision, restructure into `engine/`, `api/`, `logging_service/` |
| 2 | DONE - Leader: sorted insertion (`bisect.insort`). Member B: `simulator/config.py`, `simulator/order_generator.py` (pure order generation, not yet wired to ring buffer). Member C: `frontend/tests/` scaffold — structural page tests |
| 3 | Leader: price-time priority matching — full match |
| 4 | Member B: `simulator/market_simulator.py` — start/pause/resume/stop, calls `write_order()` |
| 5 | Leader: partial matching + remaining-quantity-stays-on-book |
| 6 | Member B: `database/models.py`, `database/sqlite_manager.py` — schema, `save_trade()` |
| 7 | Member C: `api.js` skeleton — functions defined, not yet callable (no server exists yet) |
| 8 | Leader: latency capture + matching unit tests |
| 9 | Member B: `get_recent_trades()`, `get_trade_history()`, `get_statistics()`, `clear_database()` |
| 10 | Leader: centralized logging service (`logging_service/`) |
| 11 | Member B: simulator + database unit tests |
| 12 | Leader: background engine runner thread (ring buffer -> order book, continuous) |
| 13 | Leader: FastAPI skeleton + `GET /api/orderbook` |
| 14 | Leader: `GET /api/trades`, `GET /api/stats` |
| 15 | Member C: wire `api.js` for real against live endpoints |
| 16 | Leader: `GET /api/logs`, `GET /api/buffer` |
| 17 | Leader: `POST /api/start`, `/stop`, `/pause`, `/resume` |
| 18 | Member C: wire Start/Pause/Resume/Stop buttons to real POST calls |
| 19 | Leader: WebSocket server (`ws://localhost:8000/ws`) + broadcast loop |
| 20 | Member C: wire `websocket.js` for real (replace `setInterval` fakes) |
| 21 | Leader: integration — simulator -> ring buffer -> engine -> database -> API |
| 22 | Integration tests: engine + API + WebSocket, end to end |
| 23 | Member C: real `frontend/tests/` (API calls, WS reconnect, button behavior) |
| 24 | Error handling, edge cases, bug fixes from integration |
| 25 | Final polish, documentation, deployment notes |

---

## Reference: original assignment scope (now solo)

### Member A — `shared/` — Complete (pre-existing)
- `serializer.py`, `ring_buffer.py`, `shared_memory.py` — real mmap,
  zero-copy, circular queue, process-safe (`multiprocessing.Lock`)
- `tests/test_ring_buffer.py` — 5/5 passing

### Member B scope — `simulator/`, `database/`
Full spec: `__ChronosMatch_Member_B.pdf`. In progress per plan above.
**Note:** root `simulator_starter.py` still imports the deleted
`shared_interface` module (removed Day 1) — it will be fully replaced
by `simulator/market_simulator.py` on Day 4, not patched.

### Member C scope — `frontend/`
Full spec: `__ChronosMatch_Member_C.pdf`. UI already built; wiring
in progress per plan above.
**Note:** root `dashboard_starter.py` (old curses terminal UI) still
imports the pre-restructure `order_book` path. Superseded by the web
dashboard — will be retired rather than fixed, during Day 21
integration.

See `HOW_TO_RUN.md` for environment setup and how to run each piece.
See `CHANGELOG.md` for what actually shipped each day.
