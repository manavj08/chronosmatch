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

## Day 2 — Leader + Member B + Member C (solo from here on)

**Ownership change:** Members B and C are no longer contributing.
All remaining work in the project — Leader's engine/API, Member B's
simulator/database, Member C's frontend wiring — is being completed
solo, one role's task per day going forward (see `TASKS.md` for the
revised 25-day plan).

### Leader — sorted order insertion
- `engine/order_book.py`: `insert_order()` now inserts each order into
  its correct sorted position using `bisect.insort()`, instead of a
  plain append.
  - `buy_side` stays sorted descending by price (best/highest bid at
    index 0)
  - `sell_side` stays sorted ascending by price (best/lowest ask at
    index 0)
  - Equal-price orders keep arrival order (time priority) since
    `insort` is stable relative to the sort key
- `get_top_levels()` docstring updated — it was already just a slice,
  but the slice is now genuinely sorted instead of insertion order
- Added `engine/tests/test_insert_order.py` — 5 new tests: descending
  buy sort, ascending sell sort, best-bid/best-ask at index 0, time
  priority at equal price, `depth` parameter behavior

### Member B — simulator config + order generation (new package)
- `simulator/config.py`: `ORDERS_PER_SECOND`, `PRICE_MIN`/`PRICE_MAX`,
  `MIN_QUANTITY`/`MAX_QUANTITY`, `BUY_PROBABILITY`, per spec
- `simulator/order_generator.py`: `generate_order()` builds one random
  order in the agreed shared format; `next_order_id()` gives
  incrementing ids. **Not yet wired to the ring buffer** — that's
  `market_simulator.py`'s `start_simulation()` etc., landing Day 4.
- Added `simulator/tests/test_order_generator.py` — 5 tests: required
  keys, valid side, price/quantity within configured range,
  incrementing ids

### Member C — frontend test scaffold
- Added `frontend/tests/test_pages_exist.py` — structural tests since
  there's no JS build tooling in this project (plain pytest against
  the static HTML): all 7 pages exist, dashboard references its
  chart/websocket/dashboard scripts, all pages have a responsive
  viewport meta tag
- **Real finding, not a test bug:** `dashboard.html` never includes a
  `<script src="js/api.js">` tag at all, even though the file exists.
  Documented as `test_api_js_not_yet_linked_in_dashboard` rather than
  silently added, since `api.js` is still empty — linking an empty
  script now would be premature. Real wiring + the `<script>` tag both
  land together on Day 15.

### Tests
`pytest -v` → 23/23 passing (5 ring buffer, 4 engine wiring, 5 sorted
insertion, 3 frontend structure, 5 order generation, 1 documented gap).

### Notes for Day 3
`match_order()` is still a placeholder — it calls `insert_order()`
and nothing else. Day 3 adds real price-time priority matching on top
of this sorted structure (best bid/ask are now always at index 0,
which is what Day 3's crossing logic will check).
