# Windows test failures — what was wrong and what changed

`pytest -v` on Windows (Python 3.14) reported **6 failures**: 51 passed,
6 failed, 10 skipped. The same suite was green on Linux.

None of the failures were caused by the IPC protocol, the cross-process
locking, or the matching engine. Those were correct. Three defects
produced all six failures, and two of them are the kind that POSIX
silently forgives and Windows does not.

Current state: **62 passed, 10 skipped** without the Cython engine built;
**147 passed, 0 skipped** once it is built with `python setup_demo.py`.
A fourth issue, found afterwards while running the demo, is covered in
section 5.

---

## 1. The lock file descriptor was never closed

**Symptom** — 4 failures:

```
PermissionError: [WinError 32] The process cannot access the file
because it is being used by another process: '...ring_buffer.mem.lock'
```

**Cause.** `_CrossProcessLock` opens its handle with
`os.open(lock_path, os.O_CREAT | os.O_RDWR)`. That returns a raw integer
file descriptor, not a Python file object, so nothing reclaims it
automatically. `SharedRingMemory.close()` closed the mmap and the backing
file but not the lock fd — and no test called `close()` at all. Around
twenty `RingBuffer(create=True)` calls across the suite, zero closes.

POSIX lets you delete a file that still has open handles, so the leak
was invisible on Linux. Windows refuses, so every test that started by
cleaning up its backing files failed.

**Fix.** `_CrossProcessLock.close()` (idempotent, with a `__del__`
backstop), called from `SharedRingMemory.close()`. `RingBuffer.close()`
added. Both classes are now context managers. Construction is also
exception-safe: a `SharedRingMemory` that fails partway through
`__init__` releases whatever it already opened.

## 2. Creating a region truncated a file that might still be mapped

**Symptom** — 1 failure:

```
OSError: [Errno 22] Invalid argument: '...ring_buffer.mem'
```

**Cause.** `open(BACKING_FILE, "wb")` truncates, and Windows will not
truncate a file with a live memory mapping.

This is what turned one failure into a cascade. pytest keeps a failed
test's traceback for its report; the traceback keeps the test's frame;
the frame keeps its `RingBuffer` and its mapping — for the rest of the
session. So the throughput failure below directly caused this one in the
next test.

**Fix.** The backing file is only rewritten when it is absent or the
wrong size; otherwise the header is reset through the mapping. Attaching
handles also read the creator's capacity from the header before mapping,
so a process that guesses the capacity wrong maps the region that
actually exists rather than a short one it can index past the end of.

## 3. The throughput floor was calibrated on one machine's OS

**Symptom** — 1 failure:

```
AssertionError: Throughput regressed: 54755.3 orders/sec
assert 54755.3 > 60000
```

There were two separate things here.

**The assertion measured the wrong thing.** Cross-process locking costs a
syscall per acquire and per release, and Windows' `msvcrt.locking` is
materially more expensive than POSIX `flock`. The hardcoded 60,000
floor therefore encoded the reference machine's *lock throughput*
alongside the async design it was meant to test. A test that fails
because of the OS it runs on is not a regression test.

**There was also a real stall.** `_write_with_backoff` went straight to
`asyncio.sleep(0.001)` when the buffer was full. A 1 ms request is not
honoured as 1 ms everywhere — on Windows the event loop's wait
granularity is the system timer tick, ~15.6 ms by default. At a high
target rate the buffer fills every tick, so the producer paid that stall
continuously while the consumer drained in a fraction of the time and
then idled.

**Fix, both parts.** The first retries now use `asyncio.sleep(0)` — a
bare yield, no timer armed — which is the right primitive anyway, since
"buffer full" almost always just means the consumer has not been
scheduled yet. Timed backoff still applies after a couple of yields for
the case where the consumer is genuinely slower.

The test now measures the machine's own raw IPC ceiling first (plain
synchronous write/read pairs, no asyncio anywhere) and asserts the
firehose reaches at least 40% of it. That is portable, and it asserts
something stronger than the old absolute number did: that the async
layer is not the bottleneck. Measured at ~76% on the reference machine.

## 4. Root cause behind all of it: one global backing file

Every process and every test opened the same module-global
`BACKING_FILE`. `backing_file` is now a constructor parameter,
defaulting to that global. Tests get isolated files via the new
`conftest.py` fixtures, so a single failure can no longer poison the
tests that follow it.

---

## Files changed

| File | Change |
|---|---|
| `shared/shared_memory.py` | Lock fd closed; no truncation of mapped files; `backing_file` parameter; `lock_path_for()` and `reset_shared_region()` helpers; context manager |
| `shared/ring_buffer.py` | `close()`, context manager, `backing_file` passthrough |
| `simulator/market_firehose.py` | Backoff yields before it sleeps |
| `conftest.py` | **New.** `ring_buffer` and `shared_ipc_path` fixtures, session cleanup |
| `simulator/tests/test_firehose_throughput.py` | Machine-relative threshold; new backoff-stall guard |
| `tests/test_ring_buffer.py` | Fixture-based; 4 new regression tests |
| `tests/test_cross_process_*.py` | Isolated per-test paths, children close their buffers |
| `engine/tests/`, `matching_engine/tests/` | Fixture-based |
| `run_*.py`, `audits/*.py`, `simulator/load_test.py` | Use `reset_shared_region()` |
| `benchmarks/throughput_benchmark.py` | Buffers scoped with `with` |
| `dashboard/live_dashboard.py` | `try/finally` so Ctrl-C releases the mapping |

## How the fixes were checked

Both regression guards were verified by deliberately reintroducing the
bugs:

- Re-adding a per-order `asyncio.sleep()` drops throughput to 4% of the
  raw IPC ceiling and fails the test with a message naming the cause.
- Removing the `lock.close()` call leaves the fd open — confirmed with
  `os.fstat` on the descriptor after `close()` returns.

Also verified: the suite is stable across repeated runs; no stray
`ring_buffer.mem*` files are left in the project root;
`simulator/load_test.py` sweeps all seven target rates in one process
(10k → 500k, reaching 99.8% of the 100,000/sec spec target — a sweep
that could not have completed on Windows before, since each iteration
deletes a file the previous one still had mapped); and
`benchmarks/throughput_benchmark.py` runs all four stages end to end.

## One thing to confirm on your machine

This work was done on Linux, where the two handle bugs are invisible by
construction. The reasoning for each is specific and the mechanism is
well understood, but **the decisive check is `pytest -v` on the Windows
box**.

The absolute throughput figure there depends on Windows lock-syscall
cost, which cannot be measured from a Linux machine. The test now adapts
to whatever that machine can do, so it should pass regardless — but the
number it reports is worth recording, and
`python -m benchmarks.throughput_benchmark` will give you the full
breakdown.


---

## 5. `run_demo.py` reported success after a child process crashed

**Symptom.** On a fresh checkout:

```
ModuleNotFoundError: No module named 'order_book'
...
Demo finished. Both processes exited cleanly.
```

**The import error is expected.** `order_book` is the compiled Cython
extension. It is deliberately not committed (`.gitignore` excludes
`*.pyd` / `*.so`), and HOW_TO_RUN.md step 2 covers building it:

```
python setup_demo.py
```

That needs a C compiler — on Windows, Visual Studio Build Tools with
the "Desktop development with C++" workload. Run it once after a fresh
clone or pull, then `python run_demo.py` works. This is also why 10
tests were skipping; with the engine built the suite runs 147 passed,
0 skipped.

**What was an actual defect** is that the demo declared success anyway.
The runners printed "Both processes exited cleanly" unconditionally
after `join()`, never looking at an exit code, and exited 0. The
matcher died on import and the demo reported a clean finish. For
something you're demoing to a client, that's the worst possible
failure mode — it hides the problem instead of surfacing it.

**Fixed**, two ways:

- `report_exit_status()` in each runner checks every child's
  `exitcode`, names any that failed, and exits non-zero.
- `require_compiled_engine()` runs in the parent before any child
  starts, so a missing engine gives one clear message naming the fix
  rather than a traceback buried under fifty lines of generator output.

**Verified.** Unbuilt: clear message, exit 1. Built: the full demo runs
end to end — two processes over shared memory, 50 orders, 30 trades
matched with per-trade latency — and reports `All processes exited
cleanly (exit codes: generator 0, matcher 0)`.


---

## 6. The compiled-engine guard missed the audit and benchmark scripts

Section 5's `require_compiled_engine()` was added to the four
`run_*.py` demos only. `audits/engine_verification.py` and
`benchmarks/level_bucketing_benchmark.py` import the compiled engine
the same way and still produced a raw `ModuleNotFoundError` traceback.

Root cause of the miss: the helper had been copy-pasted into each demo
rather than written once. Four copies is how a fifth caller gets
overlooked.

**Fixed.** `require_compiled_engine()` now lives in a single
`engine_check.py` at the project root; the duplicates are gone and all
six entry points import it. With the engine unbuilt, every one of them
prints the same message and exits 1.


---

## 7. Last leaked-handle site, plus a throughput pass

`benchmarks/serialization_comparison.py` was the one file the earlier
passes missed --- it monkeypatched the backing-file globals, never
closed its buffer, then tried to delete both files, giving the same
`WinError 32`. Fixed: the monkeypatch is gone (`backing_file` is a
parameter now) and the buffer is scoped with `with`.

The load sweep also showed Windows peaking near 78,000 orders/sec,
below the 100,000/sec spec target. Two changes target that:

- **Header path.** `update_header()` re-read the whole header just to
  recover `capacity`, which the caller already had; `read_header()`
  sliced the mmap before unpacking, allocating per call. Both are on
  the hot path, inside the lock. Fixed with `unpack_from`/`pack_into`
  and passing `capacity` through. **+26%** measured, platform-neutral.
- **Windows lock syscalls.** `msvcrt.locking()` does not move the file
  position, so the `os.lseek` on every acquire and release was four
  redundant syscalls per order round trip. Now seeked once at open ---
  but **verified, not assumed**: the lock probes its own behaviour at
  startup and keeps the per-call seeks if the position does not hold.
  A wrong assumption here would mean two processes locking different
  bytes, which is silent data loss rather than an error, so it is not
  something to take on documentation alone.

Reference machine: peak throughput **148,290 → 197,313 orders/sec
(+33%)**, suite still 147 passed / 0 skipped.

**Re-measure on your machine** — `python simulator/load_test.py` and
`python -m benchmarks.throughput_benchmark`. The Windows ceiling is a
lock-syscall property that cannot be measured from Linux.


---

## 8. The headline throughput number was being under-reported

On the Windows target machine:

| Measurement | Result |
|---|---|
| `audits/ipc_audit.py` — 1M orders, two OS processes | **120,117/sec**, 0 lost, 0 duplicated, in order |
| `simulator/load_test.py` — single process | 88,675/sec peak |
| `throughput_benchmark.py` stage [4] — single process | 69,768/sec |

The audit **exceeds the 100,000/sec spec target**. The other two look
like they miss it. Not a contradiction: the audit runs a producer
process and a consumer process on separate cores, which is the shipped
architecture. The other two run producer and consumer as asyncio tasks
sharing one event loop on one thread, so they take turns — measuring
self-contention, not capacity.

Cross-check: that machine's raw single-process write+read ceiling is
109,711 pairs/sec, and the sweep reaches 88,675 — about 81% of it. The
async layer is not losing throughput; one thread is simply doing both
jobs.

**The defect was the reporting**, not the code. `load_test.py` printed
its pessimistic figure directly above "Spec target: 100,000 orders/sec"
with no context. Both benchmarks now state what they measure and point
at `audits/ipc_audit.py` as authoritative.

**For the client, the number to quote is 120,117 orders/sec** — one
million orders across two real OS processes, every one delivered
exactly once and in order.
