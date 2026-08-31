# Best practices

## Keep tools small and explicit

Use one action per function, narrow annotations, short docstrings, and stable names.
Prefer JSON-native return values over custom objects. Use `version` as application
metadata when a contract changes; Samsarix Core does not route versions for you.

## Treat calls as untrusted input

Type validation does not replace authorization. Re-check tenant, user, path,
resource, and quota permissions inside the tool. Prefer allowlists and resolved
resource IDs over raw filesystem paths or shell fragments.

Use `ToolRuntime(policy=...)` for centralized defense in depth when every valid call
must pass an application-owned allow/deny decision. Keep the policy small, cancellation
friendly, and free of side effects. It sees a detached but sensitive argument snapshot;
do not log that snapshot, and return an explicit `ToolPolicyDecision` rather than
raising for an expected denial. A request-local `ContextVar` is one way for a trusted
host to expose already-authenticated scopes without adding credentials to tool schemas.
The policy is not authentication, a tenant quota store, or durable human approval.

Never register a callable merely because an untrusted client supplied its import
path. The registry is for trusted application code, not dynamic code loading.

## Protect sensitive data

Leave `expose_exceptions=False` in shared environments. Do not place credentials in
tool descriptions, tags, defaults, arguments sent to a model, outputs returned to
an untrusted caller, or external logs.

Samsarix Core itself does not log call content. Its opt-in MCP operational events
contain only status, duration, invocation ID, and an application-approved tool
identifier. If the host adds other logging or tracing, redact inputs, outputs,
exception messages, paths, tenant identifiers, and authorization material by default.

For per-invocation traces or service-level indicators, opt in with
`ToolRuntime(lifecycle_handler=...)`. The immutable events omit call content, but tool
names disclose application structure, invocation IDs are correlatable, and an unknown
requested name can be attacker-controlled. Keep the synchronous callback non-blocking,
allowlist metric labels, and hand network export to a bounded/batched host processor.
See the [lifecycle observability guide](OBSERVABILITY.md) for an OpenTelemetry adapter
that deliberately omits sensitive argument and result attributes.

## Bound every external dependency

Use finite positive execution timeouts, not NaN or infinity. `None` on a decorator
or invocation inherits a deadline rather than disabling it. Invalid settings are
rejected, including integers too large to convert to a finite float.

The runtime requests cancellation when an async deadline expires; waiting for that
cancellation can exceed the deadline if cleanup is slow or suppresses cancellation.
A sync function's thread cannot be force-stopped. Set connect/read/query/process
timeouts in the tool itself, make cancellation-friendly async calls, and make side
effects idempotent when the caller might retry after a timeout.

For a runnable example of application-owned transactions and duplicate suppression,
see [transactional tools and safe replay](SIDE_EFFECTS.md). Its SQLite reservation
commits a stock change and its request ledger together, rejects conflicting key reuse,
and replays an ambiguous committed result after timeout or restart. Core's idempotency
annotation does not provide those guarantees by itself.

Register a tool with `max_concurrency=N` when its downstream API, database pool, model
deployment, or other resource has a lower safe concurrency than the runtime as a whole.
Choose the limit from measured capacity and the dependency's quota. Samsarix acquires
this tool-specific slot before a global execution slot, preserving unrelated tool
availability while the constrained tool queues.

The per-tool concurrency limit is an in-process execution bulkhead, not a request-rate
limit, tenant quota, or process sandbox. When the dependency also has a sustained
request quota, add `rate_limit=ToolRateLimit(...)`. The token bucket is checked
immediately before tool start and returns a safe retry delay instead of waiting. Combine
both controls: concurrency protects simultaneous downstream work while rate protects
starts over time. Keep total admission finite and set downstream I/O deadlines.
See the vendor-neutral [bulkhead pattern guidance](https://learn.microsoft.com/en-us/azure/architecture/patterns/bulkhead)
for the reliability trade-offs and complementary controls.
See [per-tool rate limits](RATE_LIMITS.md) for token accounting, safe retry behavior,
primary references, and process-local limitations.

When repeatedly calling a known-failing dependency would waste capacity or amplify an
incident, add `circuit_breaker=ToolCircuitBreaker(...)`. Choose the consecutive-failure
threshold and recovery interval from observed failure modes and recovery time. Monitor
both trips and open-circuit rejections. Keep dependency connect/read/write deadlines:
the breaker reacts to observed outcomes and does not interrupt a hung operation by
itself. It also does not retry. See [per-tool circuit breakers](CIRCUIT_BREAKERS.md) for
counting, half-open probes, manual reset, primary references, and process-local limits.

Choose the runtime-wide `max_concurrency` from aggregate downstream capacity, not CPU count alone. Set
`max_pending_invocations` to the total policy/execution work one process can safely
hold; monitor `busy` and `peak_pending_invocations` to find sustained saturation.
Tune `max_batch_size`,
`max_argument_bytes`, `max_output_bytes`, `max_value_depth`, and `max_value_nodes`
below upstream transport limits, with enough headroom for legitimate contracts.
Keep `ToolRegistry.max_tools` close to the catalog size you actually expose.
For stdio MCP servers, also tune `max_in_flight_requests` to bound calls waiting
behind the runtime's execution limit.

For long-running async tools, report meaningful phase or item-count progress only
when work actually advances. Keep values strictly increasing and tune
`max_progress_updates` plus `max_progress_message_bytes` below client and
transport limits. Progress messages cross the protocol boundary and may be logged
or displayed, so keep document content, paths, credentials, and tenant data out of
them.

Enable experimental MCP tasks only for work that benefits from deferred result
retrieval. Prefer `task_support="optional"` while client support is uneven. Keep
`max_retained_tasks` below downstream capacity, use the shortest practical task
TTL, and remember that the final result remains in memory until expiry. Local
stdio does not expose `tasks.list`; a network adapter must bind get/result/cancel
to authenticated requestor identity and add per-requestor quotas and rate limits.

These controls are process-local. A network host still needs authentication,
per-principal admission, shared tenant quotas, distributed rate limits when it has more
than one process, and aggregate memory/connection limits.

MCP recommends a client-side human confirmation surface for tool calls. Preserve that
UI even when the server also uses a programmatic policy gate; annotations are hints and
server policy cannot prove that a person reviewed a call. See the official
[MCP tool interaction guidance](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).

## Handle results deliberately

Branch on `ToolStatus`; do not infer success from a truthy output. A `busy` result is
retryable because no tool or policy code ran, but use capped exponential backoff with
jitter rather than retrying immediately. A `rate_limited` result also means tool code
did not run; wait at least `error.details["retry_after_ms"]`, add bounded jitter for
competing callers, and remember that the hint does not reserve the next token. A
`circuit_open` result also means this call did not run; its retry delay may be absent
while another recovery probe is active. Retry only after bounded backoff and only when
the tool's side-effect semantics allow it. Other failures remain non-retryable because
a timed-out sync function may still finish and
cause its side effect. Apply any broader retry policy only when the tool's semantics
make that safe.

Let caller cancellation propagate. Use `async with ToolRuntime(...)` so resources
close on success and failure. Context-manager close does not wait for a timed-out
sync thread. During controlled shutdown, stop upstream admission and call
`await runtime.aclose(wait_for_sync=True, timeout=<deadline>)`; treat a `False`
result as a failed quiescence check rather than assuming the side effect stopped.

## Test contracts, not mocks

Test schema output, missing/extra/wrongly typed arguments, successful sync and async
calls, output validation, failure redaction, timeout behavior, cancellation, and
concurrency limits. Install the built wheel in an isolated environment before a
release; importing from the source checkout alone does not validate packaging.
