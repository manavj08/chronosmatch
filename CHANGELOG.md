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
