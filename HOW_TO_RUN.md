# How to Run — ChronosMatch Skeleton

Windows, Command Prompt or PowerShell.

## 1. Setup (once per teammate)

```
cd chronosmatch
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## 2. Verify the skeleton works

```
python -m unittest test_skeleton.py -v
```

All 6 tests should pass. If they don't, fix that before building on top of it.

## 3. Run each piece independently

Each file works standalone against the in-memory stub buffer in
`shared_interface.py` — no need to wait for teammates' code.

```
python order_book.py           # matching engine smoke test (writes 2 fake orders, processes them)
python ring_buffer_stub.py     # Member A: mmap pack/unpack round-trip demo
python simulator_starter.py    # Member B: generates random orders (Ctrl+C to stop)
python dashboard_starter.py    # Member C: live terminal UI with fake data (Ctrl+C to exit)
```

`dashboard_starter.py` needs a real terminal window (not all IDE consoles
support `curses`) — run it directly in Command Prompt/PowerShell.

## 4. Working together day to day

- Everyone imports from `shared_interface.py` — don't edit its function
  signatures without telling the team (see `TASKS.md` → "Golden rule").
- Run `python -m unittest test_skeleton.py` after pulling teammates' changes
  to catch integration breaks early.
- Each file has a `WHAT TO DO NEXT` block at the bottom — that's your
  day-by-day checklist. Full breakdown in `TASKS.md`.

## Troubleshooting

| Problem | Fix |
|---|---|
| `ModuleNotFoundError: curses` | Run `pip install windows-curses` (already in requirements.txt for Windows) |
| `ImportError` on `shared_interface` | Run scripts from inside the `chronosmatch/` folder |
| Dashboard renders garbled/errors | Enlarge the terminal window; some IDE terminals don't fully support curses — use Command Prompt/PowerShell directly |
| Tests fail after pulling changes | Check whether a teammate renamed/changed a shared function signature |
