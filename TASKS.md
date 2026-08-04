# ChronosMatch — Team Tasks

4-person team. Everyone codes against `shared_interface.py` from Day 1 —
its function names/signatures are frozen; only the *internals* change later.

| Role | File | Owns |
|---|---|---|
| Leader (you) | `order_book.py` | Matching engine logic |
| Member A | `ring_buffer_stub.py` → `shared_interface.py` internals | Real IPC (mmap + struct) |
| Member B | `simulator_starter.py` | Order generator / load |
| Member C | `dashboard_starter.py` | Live terminal UI |

**Golden rule:** never rename or change the signature of `write_order()`,
`read_order()`, `next_order_id()`, `get_top_levels()`, or `get_last_trade()`
without telling the whole team — everyone else is importing them directly.

---

## Leader — `order_book.py`
- Day 2: implement `insert_order()` with real sorted insertion (best price first)
- Day 3: implement `match_order()` — Price-Time Priority matching
- Day 4: no code changes needed (already calls `shared_interface.read_order()`)
- Day 6: capture timestamps in `_record_trade()` for latency stats

## Member A — `ring_buffer_stub.py` → `shared_interface.py`
- Day 1–2: confirm the `struct` byte layout (`ORDER_FORMAT`) is correct and stable
- Day 2–3: run `demo_single_process()`, get the mmap round-trip working
- Day 3: switch to a **named/file-backed** mmap so two real OS processes can share it
- Day 4: replace the fake bodies of `write_order()`/`read_order()` in
  `shared_interface.py` with your real implementation — **do not rename them**

## Member B — `simulator_starter.py`
- Day 2: refine the orders/sec counter and price random-walk if desired
- Day 3: confirm ~100 orders/sec sustained throughput
- Day 4: no changes needed — still calls `write_order()` from `shared_interface.py`
- Day 6: add a stress mode (ramp `ORDERS_PER_SECOND`: 100 → 1000 → 10000)
- Day 7: start a separate SQLite persistence module for trades

## Member C — `dashboard_starter.py`
- Day 2: expand `get_fake_order_book_snapshot()` with more rows, check layout holds
- Day 3: latency line (placeholder already included)
- Day 4: confirm field names with the Leader once `get_top_levels()` is real
- Day 5: swap `get_fake_order_book_snapshot()` for real `OrderBook` calls —
  `draw_dashboard()` itself should need **no changes**
- Day 7: highlight large trades (e.g. `curses.A_REVERSE`) above a quantity threshold

---

## Integration checkpoints
- **Day 4**: Member A's real buffer goes live — Leader, B, and C should need zero
  code changes at their call sites, since they only ever imported
  `write_order`/`read_order` from `shared_interface.py`.
- **Day 5**: Dashboard switches from fake to real `OrderBook` data.
- **Day 6–7**: Stress testing + persistence layer.

See `HOW_TO_RUN.md` for environment setup and how to run each file.
