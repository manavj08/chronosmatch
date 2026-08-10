# ChronosMatch — Team Tasks & Status

4-person team. Everyone codes against the real `shared/` package
(built by Member A) from Day 1 onward. Its function names/signatures
are frozen; only internals change without notice.

**Golden rule:** never rename or change the signature of
`write_order()`, `read_order()`, `get_stats()`, `is_full()`,
`is_empty()`, `size()` without telling the whole team.

---

## Status summary (as of Day 1)

| Module | Owner | Status |
|---|---|---|
| Ring buffer / IPC (`shared/`) | Member A | Done - real mmap, all tests pass |
| Matching engine (`engine/`) | Leader | In progress - wiring (Day 1) + sorted insertion (Day 2) done, matching logic Day 3-4 |
| Simulator + DB (`simulator/`, `database/`) | Member B | Not started |
| FastAPI + WebSocket (`api/`) | Leader | Not started (Day 8+) |
| Web dashboard (`frontend/`) | Member C | UI built, zero live data - `api.js`/`websocket.js` empty/fake |

---

## Leader — 25-day plan (`engine/`, `api/`, `logging_service/`)

| Day | Work |
|---|---|
| 1 | DONE - Fix wiring bug: `engine/order_book.py` now uses real `shared.ring_buffer.RingBuffer`; resolved `shared_interface.py` name collision; project restructured into `engine/`, `api/`, `logging_service/` |
| 2 | DONE - Sorted insertion (`insert_order`, best price first, via `bisect.insort`) |
| 3 | Price-time priority matching - full match |
| 4 | Partial matching + remaining-quantity-stays-on-book |
| 5 | Latency capture + matching unit tests |
| 6 | Centralized logging service (`logging_service/`) |
| 7 | Background engine runner thread (buffer -> book, continuous) |
| 8 | FastAPI skeleton + `GET /api/orderbook` |
| 9 | `GET /api/trades`, `GET /api/stats` |
| 10 | `GET /api/logs`, `GET /api/buffer` |
| 11 | `POST /api/start`, `/stop` |
| 12 | `POST /api/pause`, `/resume` |
| 13 | WebSocket server `ws://localhost:8000/ws` - broadcast loop |
| 14 | WebSocket: order book + trade push |
| 15 | WebSocket: stats + logs push |
| 16 | Integration with Member B's simulator + DB |
| 17 | Integration tests: engine + API |
| 18 | Integration tests: WebSocket |
| 19 | Error handling / edge cases |
| 20 | Performance pass |
| 21 | API documentation |
| 22 | Manual test collection (Postman-style) |
| 23 | Final integration with A/B/C |
| 24 | Bug fixes from integration |
| 25 | Final polish, deployment notes |

---

## Member A — `shared/` — Complete
- `serializer.py`, `ring_buffer.py`, `shared_memory.py` - real mmap,
  zero-copy, circular queue, process-safe (`multiprocessing.Lock`)
- `tests/test_ring_buffer.py` - 5/5 passing
- Optional follow-up: a genuine two-process integration test (today's
  tests all run in a single process)

## Member B — `simulator/`, `database/` — Not started
See `__ChronosMatch_Member_B.pdf` for full spec. Nothing exists yet.
**Also needs to fix:** root `simulator_starter.py` currently imports
`shared_interface`, which was deleted Day 1 (superseded by
`shared/`). This file should be replaced entirely by the real
`simulator/market_simulator.py` + `simulator/order_generator.py` per
spec, not patched.

## Member C — `frontend/`, `backend/dashboard/` — UI only
See `__ChronosMatch_Member_C.pdf` for full spec.
- `frontend/js/api.js` is empty - needs real `fetch()` calls to the
  Leader's REST endpoints (available from Day 8 onward)
- `frontend/js/websocket.js` only fakes messages via `setInterval` -
  needs a real `new WebSocket("ws://localhost:8000/ws")` connection
  (available from Day 13 onward)
- Control buttons (`Start`/`Pause`/`Resume`/`Stop`) currently just
  `alert()` - need real `POST` calls
- `frontend/tests/` doesn't exist yet
- **Decision needed:** root `dashboard_starter.py` (curses terminal
  UI) still imports the old `order_book` path. Since the web
  dashboard supersedes it per your spec, recommend retiring this file
  - confirm with Member C before deleting.

See `HOW_TO_RUN.md` for environment setup and how to run each piece.
