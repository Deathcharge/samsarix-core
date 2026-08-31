# Transactional tools and safe replay

Core validates and executes tools; it does not provide transactions or remember which
business operation already committed. A timeout or disconnected client cannot tell you
whether a database write happened. The application's storage and request identity must
resolve that uncertainty. An `idempotent=True` annotation is only a behavioral hint,
not an implementation of duplicate suppression.

## Run a real local example

From a checkout or source distribution with Core installed:

```bash
python examples/sqlite_reservations.py
```

This requires a Python build with the standard-library `sqlite3` module (normally
bundled with CPython). Core itself still has no SQLite dependency or persistence layer.
No account, network, model, external service, or existing database is used. The example
creates a uniquely named temporary directory, initializes five `cable-usb-c` items,
verifies this journey, closes its workers, and removes only that temporary directory:

| Operation | Business result | Actual stock |
| --- | --- | --- |
| Reserve two with `order-001` | `reserved`, `available: 3` | 3 |
| Replay the same request and arguments | Same saved result | 3 |
| Reuse `order-001` for three items | `idempotency_conflict` | 3 |
| Recreate the runtime and replay | Same saved result | 3 |
| Read current inventory | `available: 3` | 3 |

The printed JSON contains `first`, `replay`, `conflict`, `after_restart`, and
`current_stock`. The example exits nonzero if its verified outcomes differ. The test
suite additionally proves replay from a separate Python process against the same file.
`mcp_inventory_server.py` and the policy-gate example remain previews; running
them does not start writing to this database. The SQLite example's new MCP mode
below is a separate, explicitly host-enabled write path.

## Use the persistent store from an MCP client

These `init` / `serve` commands are new in the current source checkout; they are
not in the immutable a10 source archive. They work with Core `2.0.0a10` installed.
Use a host-owned directory and a new database filename:

```bash
python examples/sqlite_reservations.py init inventory.sqlite3 --stock 5
python examples/sqlite_reservations.py serve inventory.sqlite3
```

Initialization prints one JSON result and exits. It never overwrites an existing
file or creates missing parent directories. Serving opens only an existing store
and checks required example tables/columns without migrating or repairing them.
The schema check is not a validation of arbitrary uploaded databases. A failed
initialization may leave a file requiring host inspection; rerunning never clears it.

`serve` waits for newline-delimited MCP messages, not interactive terminal input.
Configure its command and arguments in a trusted local MCP client; use absolute paths
for that client's Python interpreter, this script and the database. The default server
can read stock, but its host policy denies **every** reservation, including saved
replays. Both tools remain discoverable with conservative read/write annotations.
Clients cannot choose a database path or enable writes through tool arguments.

To permit real reservations, the host must explicitly launch:

```bash
python examples/sqlite_reservations.py serve inventory.sqlite3 --allow-reservations
```

Add `--modern` for the opt-in MCP `2026-07-28` path. The default protocol remains
`2025-11-25`; enabling modern support still accepts legacy initialization first.
This server does not enable tasks or operational logging. The host write flag is
not authentication or proof of user consent: configure approval in the client too.
Do not expose this single-tenant local process as an unauthenticated network service.

Call `reserve_inventory` with:

```json
{"sku":"cable-usb-c","quantity":2,"request_id":"order-001"}
```

The MCP result has `isError: false` and structured content
`{"status":"reserved","available":3}`. Repeat the identical call, or stop/restart
the server on the same file and replay it: the saved result remains three, without
another decrement. Reusing that ID for quantity three returns `idempotency_conflict`.
Business refusals have `isError: false`; inspect `structuredContent.status`. Host
policy denial and validation failures have `isError: true`. Restarting without
`--allow-reservations` denies replay too, while `check_inventory` still returns three.

`--max-requests` configures the bounded ledger (default 1,000). It never evicts entries
or authorizes reuse of old IDs. Stopping the server retains the database and ledger;
the no-argument `demo` still uses disposable data. Database files and SQLite sidecars
are excluded from Git's default add and source distributions, not encrypted or deleted.
The host remains responsible for backups, access control and eventual removal.

Serving caps messages at 16 KiB and admitted protocol calls at eight, on top of the
existing runtime budgets. EOF closes protocol work and waits up to five seconds for
surviving workers; failure is reported, not called successful shutdown. That bounded
quiescence wait cannot forcibly stop a blocked filesystem operation or Python thread,
and interpreter exit may still wait for such work. Diagnostics go only to stderr and
omit database paths/SQL error details. CLI failures exit 2; interruption exits 130.

The installed-wheel gate launches eight independent server processes across both
protocols. It tests default denial, enabled writes, replay after restart, conflicting
IDs, full-ledger refusal, invalid input, empty lookup and clean EOF. After every
process it independently reads SQLite stock and ledger rows. Checker negative controls
reject a fake passing conversation with no durable write and a missing denial signal.
This is reproducible public reference evidence, not third-party adoption or power-loss
durability certification.

## The application contract

The host selects the database path when it constructs `InventoryStore`; clients can
only supply `sku`, `quantity`, and `request_id`. The host owns all initialization,
permissions, schema changes, backups, and lifecycle. `create_database` refuses an
existing path rather than clearing it. Normal operations use SQLite URI `mode=rw` or
`mode=ro`, preventing silent recreation of a missing store.

`create_runtime(store, policy=...)` registers a read-only lookup and a state-changing,
idempotent reservation tool. The latter is conservatively marked destructive because
it decreases available stock. Both return named `TypedDict` contracts. The runtime
bounds concurrency to four, pending calls to 32 and input/output to 4 KiB. The writer
also has a one-call bulkhead per runtime, but the database transaction—not that local
limit—protects concurrent writers from different runtime instances.

The reservation transaction uses the following sequence:

1. Validate a 1–64-character ASCII identifier and integer quantity of 1–1,000.
2. Acquire a SQLite write transaction with `BEGIN IMMEDIATE`.
3. Look up the request ID. Identical arguments return the saved result; different
   arguments return a conflict without exposing the previous request's contents.
4. Reject a new request if the ledger has reached its configured row limit.
5. Read stock, conditionally decrement it, and insert the request plus terminal result
   in the **same transaction**.
6. Commit before returning. Roll back both writes if any statement or commit fails.

SQL values use bound parameters, and each sync invocation creates and closes its own
connection on its worker thread. SQLite lock waiting is capped at 250 ms per lock
attempt; the normal runtime deadline is two seconds. These are example settings, not
a guarantee that a filesystem operation or Python thread can be forcibly stopped.
The implementation follows [SQLite's transaction semantics](https://www.sqlite.org/lang_transaction.html)
and Python's [connection and transaction behavior](https://docs.python.org/3/library/sqlite3.html).

## Distinguish execution from business acceptance

A successfully evaluated request can still be declined by the application. Inspect
both `ToolResult.status` and `result.output["status"]`:

| Business status | Ledger behavior | Stock behavior |
| --- | --- | --- |
| `reserved` | Save and replay | Decrease once |
| `insufficient_stock` / `unknown_sku` | Save and replay rejection | Unchanged |
| `idempotency_conflict` | Preserve original entry | Unchanged |
| `invalid_request` | No entry | Unchanged |
| `capacity_exceeded` | No new entry; saved replays still work | Unchanged |

Type/schema rejection, policy denial, database failure and runtime timeout use Core's
normal outer statuses. Unexpected database errors are redacted by default. No automatic
retry is added. A saved `available` value describes the original decision, not current
stock; use `check_inventory` for a fresh read. A saved insufficient-stock rejection
stays rejected after a later restock. Use a **new** request ID only for an intentionally
new business operation, not to work around a timeout or conflict.

## Timeout, cancellation and retention

The critical failure test commits a real reservation, then deliberately delays the
worker's response. The caller times out or cancels while the thread remains active.
Bounded quiescence correctly reports that it has not stopped. After the worker is
released and drained, a new runtime replays the same key without decrementing stock
again. This does not make arbitrary timed-out tools retryable: the property depends on
the atomic ledger and identical arguments in this application.

The default ledger cap is 1,000 terminal requests (host-configurable up to 100,000),
including business rejections. It does not evict old identities automatically, because
eviction can turn a delayed retry into a duplicate write. This is an example bound, not
a retention policy for a long-lived service. Plan archival and a documented replay
window before changing it; use the same limit in hosts sharing the database. Do not
delete ledger rows while accepting retries for those identities.

## Before using this pattern in a service

This is a runnable reference pattern, not a production inventory system. Add
authentication, authorization and user approval before exposing writes. The sample
request-ID namespace is single-tenant; scope keys and lookups to authenticated tenant
identity in a multi-tenant service. A request ID is not a credential. Replays must pass
authorization too; supplying a `ToolRuntime` policy applies before every invocation.

Use an application-owned local database directory that untrusted users cannot replace.
The store is not designed to open arbitrary uploaded databases or enforce filesystem
confinement against a hostile local account. It stores request IDs, SKUs and quantities
in plaintext; no telemetry is added, but the application must govern storage privacy.
SQLite's single-writer design, disk durability, backups, migrations, storage limits,
key retention, cancellations/refunds and multi-host deployment need their own design.
No power-loss recovery, encrypted storage, distributed transaction, external charge,
or third-party production deployment is claimed by these tests. An external side
effect cannot be made atomic merely by adding a row to this local database.
