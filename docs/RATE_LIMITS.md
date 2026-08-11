# Per-tool rate limits

Samsarix Core can apply an opt-in token bucket to one exact tool registration. This is
useful when a local tool calls an API, model deployment, database service, or other
dependency with a sustained request quota that is lower than the runtime's execution
capacity.

```python
from samsarix_core import ToolRateLimit, ToolRuntime

runtime = ToolRuntime(max_concurrency=8)
runtime.register(
    query_vendor_api,
    max_concurrency=2,
    rate_limit=ToolRateLimit(calls=60, period_seconds=60, burst=5),
)
```

This bucket starts with five tokens, refills at one token per second, and spends one
token immediately before each actual tool start. The two-call bulkhead independently
bounds simultaneous work. `burst` defaults to `calls`, so set it explicitly when the
dependency permits a smaller burst than its sustained allocation.
`calls` and `burst` are positive integers no larger than `2**53 - 1`, preserving exact
single-token accounting; `period_seconds` and the derived refill and retry-delay
magnitudes must be positive and finite.

## Result contract

Core never waits for a rate token. If no token is available when execution is ready to
start, it returns:

```json
{
  "status": "rate_limited",
  "error": {
    "code": "tool_rate_limited",
    "message": "Tool invocation rate limit is temporarily exhausted",
    "retryable": true,
    "details": {"retry_after_ms": 1000}
  }
}
```

The numeric retry delay is the minimum time observed at the rejected start. It is not a
reservation: another call can consume the next token. Clients should wait at least that
long, add bounded jitter when many callers may retry together, and retry side-effecting
tools only when application semantics make that safe.

The error contains no arguments, output, exception text, policy context, or progress
message. `RuntimeMetrics.rate_limited` counts rejections without tool names or content,
and a lifecycle handler receives the paired terminal `rate_limited` status. MCP returns
the same structured tool execution error with `isError: true`; a task-augmented call
reaches task status `failed` and retains that exact safe result.

## Ordering and token accounting

One invocation proceeds in this order:

1. bounded runtime admission;
2. tool lookup plus argument resource and schema validation;
3. optional host policy;
4. optional circuit permit;
5. optional per-tool and global concurrency acquisition;
6. queued circuit-permit revalidation;
7. token check and consumption;
8. tool execution.

Missing tools, invalid calls, explicit policy denials, policy failures, and calls that
time out or are cancelled before the execution controls are acquired do not spend a
token. Once a token is consumed, later cancellation, timeout, output validation failure,
or tool failure does not refund it because the downstream operation may already have
started. Waiting for a concurrency slot is covered by the ordinary invocation timeout;
there is no additional rate-limit queue.

Replacement is explicit deployment policy. Replacing a tool discards the old bucket,
and omitting `rate_limit` leaves the replacement unrestricted apart from other runtime
controls. Direct registry mutation does not add a rate policy; use `ToolRuntime.register`
when this control is required.

An open circuit rejects before the bucket is checked, so it does not spend a token. A
rate rejection while holding the single half-open probe does not count as a dependency
failure or leave the breaker stuck; the next eligible caller can probe after a token is
available. See [per-tool circuit breakers](CIRCUIT_BREAKERS.md).

## Scope and limits

The bucket belongs to one `ToolRuntime` process and one exact registration. It is
dependency-free, uses a monotonic clock, stores no call content, and coordinates direct,
batch, ordinary MCP, and task-augmented MCP starts in that runtime. It does not coordinate
multiple processes or machines, persist across restart, authenticate callers, allocate
per-principal quotas, or provide tenant fairness. A horizontally scaled or remote host
still needs a shared authenticated quota service or gateway at its trust boundary.

This design follows current primary guidance: the MCP tool security considerations say
servers must rate-limit tool invocations; AWS Well-Architected recommends rejecting
excess requests with a retry signal and identifies token buckets as an implementation
pattern; Envoy's local limiter likewise uses a token bucket and is process-local by
default.

- [MCP tool security considerations](https://modelcontextprotocol.io/specification/2025-11-25/server/tools#security-considerations)
- [AWS Well-Architected: throttle requests](https://docs.aws.amazon.com/wellarchitected/latest/framework/rel_mitigate_interaction_failure_throttle_requests.html)
- [Envoy local rate limit](https://www.envoyproxy.io/docs/envoy/latest/configuration/http/http_filters/local_rate_limit_filter)
