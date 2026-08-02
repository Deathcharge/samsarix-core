# Architecture

Samsarix Core has one narrow responsibility: turn trusted typed Python callables into
inspectable contracts and invoke them predictably inside an async application.

```text
typed function
    -> @samsarix_tool definition check
    -> ToolRegistry contract compilation
    -> JSON Schema catalog
    -> iterative argument resource preflight
    -> ToolRuntime argument validation
    -> bounded async or thread-pool execution
    -> output validation and resource preflight
    -> ToolResult
```

## Components

- `decorators.py` validates metadata and attaches immutable configuration without
  wrapping or changing the callable.
- `schema.py` owns the supported type subset, JSON Schema compilation, defaults,
  iterative resource checks, strict input validation, and JSON normalization.
- `registry.py` stores a capped set of compiled callable contracts behind a small
  thread-safe map.
- `runtime.py` owns concurrency, the sync thread pool, timeouts, cancellation,
  exception redaction, batch workers, lifecycle, and content-free counters.
- `mcp.py` owns protocol lifecycle, schema/result translation, active request
  correlation, client cancellation, and bounded concurrent stdio dispatch.
- `models.py` and `errors.py` define the public boundary types.

## Trust boundaries

The registry boundary is developer-controlled. Registered callables have the same
file, process, environment, network, and credential access as the host application.
Samsarix Core neither isolates nor authorizes them.

Invocation arguments may originate from an untrusted model or client, so the
runtime bounds size and structural complexity before recursive type validation and
before calling a function. Validation is a shape/type boundary, not application
authorization: each tool still enforces resource access, tenant isolation, quotas,
and business rules.

Exception messages are redacted by default and metrics never retain tool names,
arguments, outputs, or errors. The successful output is intentionally returned to
the caller and must be treated according to the host application's data policy.

## Concurrency and timeout semantics

One semaphore bounds executing work. Async functions run on the event loop. Sync
functions run in a private `ThreadPoolExecutor` whose worker count equals
`max_concurrency`. `invoke_many` uses a bounded worker set rather than one task per
call. Registry and batch caps bound catalog and fan-out growth; per-value byte,
depth, and node limits bound validation work. The stdio adapter separately caps
admitted tool-call coroutines so cancellation can remain responsive without
creating an unbounded wait queue. These controls do not replace host-level rate
limits or tenant quotas.

Async cancellation is cooperative. Python cannot safely kill a running thread, so
a timed-out or client-cancelled sync function may outlive its protocol result. Its
semaphore slot and actual in-flight metric remain held until the thread finishes,
preventing repeated
timeouts from filling an unbounded executor queue. `pending_sync_calls` exposes
this state. `wait_for_sync()` and the opt-in waiting form of `aclose()` provide
bounded quiescence checks; the default close remains non-blocking. Blocking sync
tools must still set their own socket/database/subprocess deadlines.

## Deliberate exclusions

The alpha has no provider SDK, network server, subprocess executor, persistent
queue, retry policy, auth layer, tracing backend, plugin loader, or distributed
coordination. Those concerns belong in adapters or later releases backed by real
use cases and operational ownership.

The repository's earlier broad prototypes are preserved under `legacy/` but are
not packaged or supported.
