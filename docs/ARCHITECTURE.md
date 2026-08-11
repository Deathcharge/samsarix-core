# Architecture

Samsarix Core has one narrow responsibility: turn trusted typed Python callables into
inspectable contracts and invoke them predictably inside an async application.

```text
definition: typed function
    -> @samsarix_tool definition check
    -> ToolRegistry contract compilation
    -> JSON Schema catalog

invocation: incoming call
    -> optional content-free lifecycle start signal
    -> fail-fast bounded runtime admission
    -> registered tool resolution
    -> iterative argument resource preflight
    -> ToolRuntime argument validation
    -> optional bounded host policy decision
    -> optional per-tool circuit permit
    -> optional per-tool execution bulkhead
    -> queued circuit-permit revalidation
    -> optional per-tool token-bucket start check
    -> bounded async or thread-pool execution
    -> optional invocation-scoped progress handler
    -> output validation and resource preflight
    -> ToolResult
    -> optional content-free lifecycle terminal signal
```

## Components

- `decorators.py` validates metadata and attaches immutable configuration without
  wrapping or changing the callable.
- `schema.py` owns the supported type subset, JSON Schema compilation, defaults,
  iterative resource checks, strict input validation, and JSON normalization.
- `registry.py` stores a capped set of compiled callable contracts behind a small
  thread-safe map.
- `runtime.py` owns concurrency, process-local per-tool circuit/rate controls, the sync
  thread pool, timeouts, cancellation, exception redaction, batch workers, lifecycle,
  and content-free counters.
- `progress.py` owns invocation-scoped async progress validation, ordering,
  resource caps, and lifecycle closure.
- `_mcp_tasks.py` owns finite in-memory task retention, secure identifiers, TTL
  cleanup, terminal state transitions, result waits, and cancellation.
- `mcp.py` owns protocol lifecycle, schema/result translation, active request
  correlation, progress-token translation, client-selected content-free operational
  logging, optional task negotiation, client cancellation, and bounded concurrent
  stdio dispatch.
- `models.py` and `errors.py` define the public boundary types.

## Trust boundaries

The registry boundary is developer-controlled. Registered callables have the same
file, process, environment, network, and credential access as the host application.
Samsarix Core does not isolate them or authenticate callers. An optional host-owned
policy can deny a validated invocation before execution, but it is not an identity
provider, permission database, or human-approval workflow.

Invocation arguments may originate from an untrusted model or client, so the
runtime bounds size and structural complexity before recursive type validation and
before calling a function. Validation is a shape/type boundary, not application
authorization: each tool still enforces resource access, tenant isolation, quotas,
and business rules. A policy receives detached copies of the resolved tool spec and
default-filled arguments so policy mutation cannot alter the registered contract or
executed call. Policy failures and invalid decisions fail closed without serializing
the snapshot.

Exception messages are redacted by default and metrics never retain tool names,
arguments, outputs, or errors. The successful output is intentionally returned to
the caller and must be treated according to the host application's data policy.
Opt-in MCP operational events reuse the public tool name and result metadata but
never copy call arguments, outputs, exception text, or validation details.
Opt-in runtime lifecycle events apply the same content-free boundary to direct,
batch, MCP, and task calls. Their requested tool name and invocation ID are still
application metadata and correlatable identifiers, so handlers belong at a trusted
host boundary and must control label cardinality and retention.
Opt-in MCP tasks necessarily retain the final tool result in memory until expiry.
They use cryptographically random IDs and expose no unauthenticated listing, but a
valid ID grants get/result/cancel access within that logical server session. A
network adapter must bind that access to an authenticated requestor.

## Concurrency and timeout semantics

The runtime admits at most `max_pending_invocations` non-terminal calls, including
calls resolving, validating, awaiting policy, awaiting execution, or executing. A
call beyond that cap returns the safe, retryable `runtime_busy` result immediately;
it does not enter a semaphore queue or retain its arguments. Content-free current,
peak, and rejection counters make saturation observable. `invoke_many` also limits
its worker set to this cap so a batch does not shed its own queued items.

One semaphore bounds all executing work. A registration can add a per-tool semaphore,
which is acquired first so calls waiting on one constrained dependency do not reserve
runtime-wide capacity. The bulkhead is bound to the exact internal registration and is
not exported in the portable schema or MCP catalog; replacing a registration cannot
inherit stale operational policy. Async functions run on the event loop. Sync functions
run in a private `ThreadPoolExecutor` whose worker count equals
`max_concurrency`. `invoke_many` bounds its worker set by pending admission capacity;
global and per-tool semaphores still bound execution. This prevents workers queued on
one constrained tool from head-of-line blocking unrelated calls that fit within the
batch's available pending capacity.

An optional circuit breaker is also bound to the exact registration and checked before
capacity is acquired. A generation-bound permit is revalidated at the execution
boundary; opening or manually resetting a circuit invalidates queued permits and late
outcomes. Breaker outcome is committed before async or thread-backed capacity is
released. Open state admits no work until its monotonic recovery interval elapses, then
reserves exactly one half-open probe. The runtime performs no automatic retries and no
background health checks.

An exact registration may also own an event-loop-local token bucket. After validation,
policy, and concurrency acquisition, the runtime checks one token immediately before
starting tool code. It never waits for a token. Rejection releases the acquired slots,
returns safe retry metadata, increments a content-free counter, and does not submit sync
work. Policy denials and calls cancelled before execution controls are acquired do not
consume tokens; a token is not refunded after execution may have started. Replacement
discards the old bucket. The limiter uses a monotonic clock and has no content-bearing
keys, but each process owns independent state.
Registry and batch caps bound catalog and fan-out growth; per-value byte,
depth, and node limits bound validation work. The stdio adapter separately caps
admitted tool-call and blocking task-result coroutines so cancellation can remain
responsive without creating an unbounded wait queue. The task store independently
caps retained entries and TTL. Process-local buckets do not replace shared rate limits,
per-principal admission, authenticated tenant quotas, or gateway abuse controls.

A second semaphore bounds async policy evaluations to `max_concurrency`. The caller's
invocation timeout covers the policy wait, decision, execution-slot wait, and tool work.
Cancellation propagates through a running policy. Policy evaluation does not increment
tool `in_flight`; explicit denials have their own content-free metric.

Async tool progress uses a context variable scoped to the runtime execution task,
so it does not alter the callable's schema. Each scope serializes updates, enforces
strictly increasing finite values, caps update count and message bytes, and closes
before the invocation returns. Context copied into a detached child task sees the
closed scope after its parent call completes and cannot emit a late notification.

Async cancellation is cooperative. Python cannot safely kill a running thread, so
a timed-out or client-cancelled sync function may outlive its protocol result. Its
global and per-tool semaphore slots and actual in-flight metric remain held until the thread finishes,
preventing repeated
timeouts from filling an unbounded executor queue. `pending_sync_calls` exposes
this state. `wait_for_sync()` and the opt-in waiting form of `aclose()` provide
bounded quiescence checks; the default close remains non-blocking. Blocking sync
tools must still set their own socket/database/subprocess deadlines.

Lifecycle callbacks run synchronously at the logical call boundary and must be
non-blocking. Ordinary callback failures cannot replace call behavior and are counted.
Core owns no exporter queue or telemetry worker; a host integrates a bounded/batched
processor. A timeout or cancellation closes the logical lifecycle even when a surviving
synchronous worker keeps physical in-flight capacity occupied.

## Deliberate exclusions

The alpha has no provider SDK, network server, subprocess executor, cross-process
task persistence, retry policy, auth layer, tracing backend, plugin loader, or
distributed coordination. Those concerns belong in adapters or later releases
backed by real use cases and operational ownership.

The repository's earlier broad prototypes are preserved under `legacy/` but are
not packaged or supported.
