# Architecture Decisions

Short, honest records of the trade-offs made in this project where a
real alternative existed — matching the rest of this codebase's style
(explain the choice, not just the result, and say what would change it).

## SQLite vs. ClickHouse for the trade ledger (Day 21)

**Decision: SQLite.**

The spec names "SQLite/ClickHouse" as alternatives for the durable
audit-trail ledger (Week 4: Resiliency). Both were considered; SQLite
was chosen and is what `database/ledger.py` implements.

**Why SQLite:**
- **Zero operational overhead.** SQLite is a library, not a server —
  `database/ledger.py` just opens a file. ClickHouse needs a running
  server process (or a managed cluster) to connect to, which is real
  infrastructure this project doesn't need to stand up to demonstrate
  a correct, durable audit trail.
- **Sufficient for this project's actual write volume.** The async
  flusher (`database/trade_flusher.py`) batches inserts on a 100ms
  interval specifically so the ledger never sits on the matching
  engine's critical path — at that batching rate, SQLite's write
  throughput is not the bottleneck anywhere this project has measured
  (see `benchmarks/`, `audits/ipc_audit.py`). The bottleneck this
  project actually cares about proving isn't a bottleneck — IPC
  serialization — is a different layer entirely (see
  `benchmarks/serialization_comparison.py`).
- **Correctness properties this project needs are native to it.**
  `INSERT OR IGNORE` on `trade_id` as the primary key
  (`database/ledger.py::save_trade`/`save_trades_batch`) gives
  duplicate-safety for free if a flusher ever restarts and re-reads
  from a stale position — no extra design work.
- **Trivial to inspect and verify.** Every demo and test in this
  project that touches the ledger opens the resulting `.db` file in a
  completely separate process afterward and re-reads it independently
  (not trusting the writer's own self-report) — `sqlite3` (stdlib) or
  any SQLite browser does this with zero setup. Verifying a ClickHouse
  table the same way needs a running server and a client.

**When ClickHouse would be the right call instead:**
- **Real production write volume**, well beyond what a single SQLite
  file (single-writer-at-a-time for the file, effectively) can sustain
  — ClickHouse's column-oriented storage and native support for
  high-throughput, high-cardinality inserts is built for exactly that
  scale, which a real production HFT ledger recording every trade
  across many symbols and venues would likely hit.
- **Analytical queries over huge trade histories** — "average latency
  by hour over the last year across 10,000 symbols" is the kind of
  query ClickHouse's columnar engine is designed to make fast; SQLite
  would need to scan far more data per query at that scale.
- **Multiple concurrent writers** — SQLite serializes writes at the
  file level; a real multi-matching-engine-instance production system
  writing to one shared ledger would want something built for
  concurrent write throughput.

**Bottom line:** SQLite is the right choice for what this project
actually needs to prove (a correct, durable, easily-verified audit
trail) without adding infrastructure it doesn't need. ClickHouse is the
right upgrade path if this ever needs to handle real production HFT
write volume or serve analytical queries at scale — noted here as the
honest "if this needs to grow" answer, not implemented, because nothing
in this project currently needs it.

## Coarse-grained (single-mutex) ring buffer, not a lock-free SPSC design

**Decision:** `shared/shared_memory.py`'s `CrossProcessLock` protects
BOTH `write_order()` and `read_order()` with one mutex, rather than
implementing a true lock-free single-producer/single-consumer ring
buffer using atomic pointer operations.

**Why:** correctness comes from serializing every buffer access through
one well-understood, standard OS primitive (`fcntl.flock` /
`msvcrt.locking`), proven correct under real load (1,000,000 orders,
two real processes, zero loss — `audits/ipc_audit.py`). A true
lock-free SPSC design needs real atomic compare-and-swap primitives on
the shared memory itself, which aren't natively available from pure
Python across independently-started processes without an additional
C extension — a meaningfully bigger undertaking for a benefit
(true concurrent producer/consumer access, not just correctness) this
project's measured throughput (~130k orders/sec sustained, see
`audits/ipc_audit.py` and `simulator/load_test.py`) doesn't currently
need. The measured cost of this choice is documented directly, not
hidden: very small buffer capacities suffer real lock-contention
overhead (an 8-slot buffer sustains roughly two orders of magnitude
less throughput than a 512-slot one — see the standalone `ipc/`
deliverable package's `test_throughput_degrades_at_very_small_capacity`
test), which is why production capacity (4096) is chosen well above
the minimum needed for correctness.

## Fixed-size struct slots, not variable-length framing

**Decision:** every order occupies exactly `SLOT_SIZE` (29) bytes in
the ring buffer (`shared/serializer.py`), rather than a variable-length
encoding (like JSON or Pickle) with a length prefix or delimiter.

**Why:** fixed-size slots mean the reader always knows exactly how many
bytes to read for the next order, with no parsing, no delimiter
scanning, and no length-prefix bookkeeping — the entire "protocol" is
"read 29 bytes at this offset." This is what makes the ring buffer's
`slot_offset(index) = HEADER_SIZE + index * SLOT_SIZE` arithmetic work
directly, and it's a meaningful chunk of why `struct` pack/unpack
measures 7-8x faster than JSON and ~2.4x faster than Pickle for the
same data (`benchmarks/serialization_comparison.py`) — those formats
both need variable-length framing precisely because their output size
varies per message, work this protocol never has to do.
