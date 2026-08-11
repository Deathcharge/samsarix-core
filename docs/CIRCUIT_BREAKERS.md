# Per-tool circuit breakers

Samsarix Core can attach an opt-in circuit breaker to one exact tool registration. It
protects a host from repeatedly calling a dependency that is already failing, while
leaving unrelated tools available.

```python
from samsarix_core import ToolCircuitBreaker, ToolRuntime

runtime = ToolRuntime(max_concurrency=8)
runtime.register(
    query_vendor_api,
    max_concurrency=2,
    circuit_breaker=ToolCircuitBreaker(
        failure_threshold=3,
        recovery_timeout_seconds=30,
    ),
)
```

The breaker starts closed. Three consecutive execution failures open it for 30 seconds.
Calls rejected while open do not wait for concurrency, consume a rate-limit token, or
run tool code. Once the recovery interval has elapsed, one caller becomes the half-open
probe. A successful probe closes the breaker; a failed probe opens it for another full
recovery interval. Other callers fail fast while that probe is active.

## Result contract

An open circuit returns a safe structured result:

```json
{
  "status": "circuit_open",
  "error": {
    "code": "tool_circuit_open",
    "message": "Tool dependency circuit is temporarily open",
    "retryable": true,
    "details": {"retry_after_ms": 30000}
  }
}
```

`details.retry_after_ms` is present while the configured recovery interval remains. It
is a hint, not a reservation. A rejection caused by another active half-open probe has
no retry delay because the probe's completion time is unknown. Clients should use
bounded jitter and retry a side-effecting tool only when application semantics make the
retry safe.

The error contains no arguments, output, exception text, policy context, or progress
message. `RuntimeMetrics.circuit_open` counts rejections and
`RuntimeMetrics.circuit_breaker_trips` counts transitions caused by a threshold or a
failed probe. Lifecycle events use terminal status `circuit_open`. MCP serializes the
same result as a tool-origin error with `isError: true`; a task-augmented call reaches
task status `failed` and retains only that safe terminal result.

## What counts as a failure

The consecutive-failure counter changes only after the host policy has allowed an
invocation and the protected execution has started or reached its caller-visible
deadline:

- a tool exception counts;
- output validation or resource-limit failure counts;
- a caller-visible timeout counts, including a timed-out synchronous worker that may
  still be stopping;
- a successful validated output resets the consecutive-failure count;
- missing tools, invalid arguments, policy denial or policy failure, runtime admission
  rejection, rate-limit rejection, progress-handler failure, and caller cancellation do
  not count.

Core does not automatically retry a failed call. Retries and circuit breaking solve
different problems: an application may add bounded retry behavior around a transient
operation, but should account for idempotency, its total deadline, and the extra load
that retrying creates.

## Ordering and concurrency

One invocation proceeds in this order:

1. bounded runtime admission;
2. tool lookup plus argument resource and schema validation;
3. optional host policy;
4. circuit permit;
5. optional per-tool and global concurrency acquisition;
6. queued-permit revalidation;
7. optional rate-token consumption;
8. tool execution and output validation.

The permit is checked again at the execution boundary. If one failure opens the circuit
while another call is waiting for capacity, the queued call is rejected instead of
reaching the dependency. Breaker outcome is recorded before capacity is released, for
both coroutine and thread-backed tools. This preserves the fail-fast boundary under
concurrency. Waiting before execution remains covered by the ordinary invocation
timeout and the runtime-wide pending-invocation cap.

## Inspection, reset, and replacement

```python
from samsarix_core import ToolCircuitState

state = runtime.circuit_state("query_vendor_api")
if state is ToolCircuitState.OPEN:
    alerted = True

runtime.reset_circuit("query_vendor_api")
```

`circuit_state(name)` returns `closed`, `open`, or `half_open` for a configured breaker,
and `None` for a registered tool without one. It reports the explicit current state;
observing an elapsed recovery interval does not reserve the single probe.
`reset_circuit(name)` returns `True` when it reset a configured breaker and `False` for
an unprotected registered tool. Both methods raise `ToolNotFoundError` for an unknown
name. A manual reset invalidates outstanding permits, so a late result from pre-reset
work cannot mutate the new state.

Replacing a tool discards its old breaker. Omitting `circuit_breaker` leaves the
replacement unprotected apart from other runtime controls. Direct registry mutation
does not add a breaker; use `ToolRuntime.register` when this control is required.

## Scope and limits

The breaker is dependency-free, process-local, monotonic-clock-based, and content-free.
It coordinates direct, batch, ordinary MCP, and task-augmented MCP calls through one
runtime. It does not coordinate multiple processes or machines, persist across restart,
identify tenants, provide a statistical sliding window, probe dependency health out of
band, or replace dependency-level connect/read/write deadlines. Deployments needing a
shared breaker should place it at a shared authenticated gateway or service boundary.

The closed/open/half-open model and fail-fast behavior follow current vendor-neutral
guidance, while the deliberately small consecutive-failure policy keeps the public
contract auditable:

- [Azure Architecture Center: Circuit Breaker pattern](https://learn.microsoft.com/en-us/azure/architecture/patterns/circuit-breaker)
- [AWS Prescriptive Guidance: Circuit breaker pattern](https://docs.aws.amazon.com/prescriptive-guidance/latest/cloud-design-patterns/circuit-breaker.html)
- [Polly circuit-breaker strategy](https://www.pollydocs.org/strategies/circuit-breaker)
- [Resilience4j circuit breaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [MCP schema: tool execution errors](https://modelcontextprotocol.io/specification/2025-11-25/schema)
