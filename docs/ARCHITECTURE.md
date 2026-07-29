# Architecture

Samsarix Core has one narrow responsibility: turn trusted typed Python callables into
inspectable contracts and invoke them predictably inside an async application.

```text
typed function
    -> @samsarix_tool definition check
    -> ToolRegistry contract compilation
    -> JSON Schema catalog
    -> ToolRuntime argument validation
    -> bounded async or thread-pool execution
    -> output validation
    -> ToolResult
```

## Components

- `decorators.py` validates metadata and attaches immutable configuration without
  wrapping or changing the callable.
- `schema.py` owns the supported type subset, JSON Schema compilation, defaults,
  strict input validation, and JSON normalization.
- `registry.py` stores compiled callable contracts behind a small thread-safe map.
- `runtime.py` owns concurrency, the sync thread pool, timeouts, cancellation,
  exception redaction, batch workers, lifecycle, and content-free counters.
- `models.py` and `errors.py` define the public boundary types.

## Trust boundaries

The registry boundary is developer-controlled. Registered callables have the same
file, process, environment, network, and credential access as the host application.
Samsarix Core neither isolates nor authorizes them.

Invocation arguments may originate from an untrusted model or client, so the
runtime validates them before calling a function. Validation is a shape/type
boundary, not application authorization: each tool still enforces resource access,
tenant isolation, quotas, and business rules.

Exception messages are redacted by default and metrics never retain tool names,
arguments, outputs, or errors. The successful output is intentionally returned to
the caller and must be treated according to the host application's data policy.

## Concurrency and timeout semantics

One semaphore bounds executing work. Async functions run on the event loop. Sync
functions run in a private `ThreadPoolExecutor` whose worker count equals
`max_concurrency`. `invoke_many` uses a bounded worker set rather than one task per
call.

Async cancellation is cooperative. Python cannot safely kill a running thread, so
a timed-out sync function may outlive its result. The executor still bounds worker
count, but blocking sync tools must set their own socket/database/subprocess
deadlines. `aclose()` does not wait forever for timed-out threads.

## Deliberate exclusions

The alpha has no provider SDK, network server, subprocess executor, persistent
queue, retry policy, auth layer, tracing backend, plugin loader, or distributed
coordination. Those concerns belong in adapters or later releases backed by real
use cases and operational ownership.

The repository's earlier broad prototypes are preserved under `legacy/` but are
not packaged or supported.
