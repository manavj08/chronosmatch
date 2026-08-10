# How to Run — ChronosMatch

Windows, Command Prompt or PowerShell.

## 1. Setup (once per teammate)

```
cd chronosmatch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Verify the project works

```
pytest -v
```

9 tests should pass (5 ring buffer, 4 engine). If they don't, fix that
before building on top of it.

## 3. Run each piece independently

```
python -m engine.order_book    # matching engine smoke test, real ring buffer
python -m shared.ring_buffer   # (importable only, no __main__ demo yet)
python -m simulator.order_generator   # order generation smoke test (Day 2)
python simulator_starter.py    # BROKEN as of Day 1 - superseded by simulator/ (Day 4)
python dashboard_starter.py    # BROKEN as of Day 1 - superseded by web dashboard
```

`dashboard_starter.py` and `simulator_starter.py` still reference the
old deleted `shared_interface.py` stub. They are flagged in
`CHANGELOG.md` and `TASKS.md` for their owning members to replace with
the real modules per the assignment docs, rather than patched here.

`dashboard_starter.py` needs a real terminal window (not all IDE consoles
support `curses`) — run it directly in Command Prompt/PowerShell, if kept.

## 4. Working together day to day

- Everyone imports from `shared/` (Member A's real package) — don't edit
  its function signatures without telling the team (see `TASKS.md` →
  "Golden rule").
- Run `pytest -v` after pulling teammates' changes to catch integration
  breaks early.
- Full day-by-day breakdown in `TASKS.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: curses` | Run `pip install windows-curses` (already in requirements.txt for Windows) |
| `ImportError` on `shared_interface` | That module was removed Day 1 — see `CHANGELOG.md`. Use `shared.ring_buffer.RingBuffer` instead. |
| `ImportError` on `order_book` | Old path. Use `engine.order_book` instead. |
| Dashboard renders garbled/errors | Enlarge the terminal window; some IDE terminals don't fully support curses — use Command Prompt/PowerShell directly |
| Tests fail after pulling changes | Check whether a teammate renamed/changed a shared function signature |
