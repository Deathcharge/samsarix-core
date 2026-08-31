# Model Context Protocol bridge

Samsarix Core can expose its trusted local tools through the Model Context
Protocol (MCP) without adding a runtime dependency. The bridge implements the
explicit protocol revisions `2025-11-25` and `2025-06-18`. These are compatibility
targets. The unreleased source also offers opt-in `2026-07-28` ordinary-tool
support through `MCPServer(..., enable_modern=True)`. The published a9 artifact
does not contain that option. Default servers keep the 2025 handshake unchanged;
newer clients can negotiate backward or use the explicit modern option below.

The supported server surface is intentionally narrow:

- lifecycle initialization and version negotiation;
- `ping`;
- `tools/list` with JSON Schema Draft 2020-12 input and output contracts;
- `tools/call` with Samsarix validation, timeouts, concurrency and opt-in per-tool
  circuit/rate controls, and safe structured errors, including optional host-policy denial;
- requested `notifications/progress` updates from cooperative asynchronous tools;
- opt-in `logging/setLevel` and content-free `notifications/message` operational
  events;
- `notifications/cancelled` for active tool calls and task-result waits;
- opt-in experimental task-augmented tool calls with `tasks/get`, blocking
  `tasks/result`, explicit `tasks/cancel`, finite retention, and bounded capacity;
- newline-delimited stdio with configurable message-size and active-request caps.

It does not implement MCP resources, prompts, sampling, `tasks/list`, durable
cross-process task persistence, HTTP transport, authentication, or authorization.
Those remain host-application concerns.

## Opt-in MCP 2026-07-28

From a checkout containing this unreleased change, install with `python -m pip
install -e .`, then launch the same read-only inventory example with:

```bash
python examples/mcp_inventory_server.py --modern
```

For an application-owned runtime, construct `MCPServer(runtime,
enable_modern=True)`. One `MCPServer` instance represents one trusted stdio
connection/process and selects an era: a successful legacy `initialize` selects
the 2025 contract; a valid modern request selects the per-request contract. This
implementation does not mix eras on that instance. Use a fresh instance/process
to switch. Protocol version, capabilities and logging are still validated on
every modern request; discovery never grants capabilities to later requests.
An unversioned pre-initialization `ping` still receives the legacy empty result
without selecting either era. A modern-versioned ping remains a removed method.

The modern path implements:

- `server/discover`, or a direct first `tools/list`/`tools/call` without discovery;
- required `params._meta` fields `io.modelcontextprotocol/protocolVersion` and
  `io.modelcontextprotocol/clientCapabilities`; missing or malformed required
  metadata returns `-32602` before tool execution;
- unsupported-version error `-32022` with `data.requested` and `data.supported`;
- `resultType: "complete"` and `io.modelcontextprotocol/serverInfo` result metadata;
- deterministic name-sorted tool discovery with `ttlMs: 0`, `cacheScope: "private"`:
  no freshness promise or permission to share a potentially private tool catalog;
- the same validated calls, bounded runtime controls, output schema/text fallback,
  progress and cooperative cancellation as the legacy bridge;
- if the host already enables operational logging, per-request
  `io.modelcontextprotocol/logLevel` filtering. Missing logLevel means no protocol
  log, including errors; overlapping calls do not share log settings. This remains
  a deprecated protocol feature, not a reason to add new logging integrations.

Optional client identity/capabilities are untrusted metadata, not authentication,
tenant identity, policy approval or permission to invoke a tool. Core never acts
on arbitrary extension capabilities. It emits only complete ordinary tool results;
it does not request roots, sampling or elicitation, so no client capability is
required beyond the required capabilities object (which can be empty).

Modern `ping`, `logging/setLevel`, task methods, subscriptions, resources and prompts
return `-32601`. Legacy task support is **not** the redesigned 2026 task extension:
modern discovery advertises no tasks/extensions or `execution.taskSupport`.
Task-required tools are omitted from the modern catalog and rejected by name;
task-optional tools remain ordinary calls. Calls containing `task`, `inputResponses`
or `requestState` are rejected before execution; no unimplemented continuation is
silently treated as a fresh write. HTTP/authentication, multi-round-trip operations,
subscriptions and the task extension are not implemented. Existing object-wrapped
scalar/array outputs remain deliberate valid schemas, not native unwrapped output.

The source's official-client checker adds an explicit mode:

```bash
python -I scripts/verify_mcp_client.py /absolute/path/to/newly-built.whl --sdk-version 2.1.1 --modern
```

It requires the official SDK 2.1.1, a wheel containing the new option, successful
modern discovery (not fallback), modern results/cache hints, per-request log
privacy, Unicode, validation errors, empty results and progress. A separate modern
session proves repeated cooperative cancellation and slot recovery. The existing
SDK 2.x CI jobs run both legacy and modern commands; SDK 1.x continues proving the
legacy path. SDK packages remain outside Core's dependencies. This is the narrow
stdio tool surface, not certification of every optional MCP feature.

Primary sources checked 2026-08-31: [revision changes](https://modelcontextprotocol.io/specification/2026-07-28/changelog),
[versioning](https://modelcontextprotocol.io/specification/2026-07-28/basic/versioning),
[request metadata](https://modelcontextprotocol.io/specification/2026-07-28/basic#_meta),
[discovery](https://modelcontextprotocol.io/specification/2026-07-28/server/discover),
[tools](https://modelcontextprotocol.io/specification/2026-07-28/server/tools),
[stdio](https://modelcontextprotocol.io/specification/2026-07-28/basic/transports/stdio),
and [request-scoped logging](https://modelcontextprotocol.io/specification/2026-07-28/server/utilities/logging).

## Run the example

Install the project, then start the example as the command for a trusted local
MCP client:

```bash
python examples/mcp_inventory_server.py
```

The process reads MCP JSON-RPC messages from stdin and writes only protocol
messages to stdout. Send application diagnostics to stderr. For stdio servers,
provide credentials through the process environment rather than protocol
arguments or command-line flags that may be logged by a launcher.

The complete server setup is in
[`examples/mcp_inventory_server.py`](../examples/mcp_inventory_server.py).

## Official Python client verification

In addition to the dependency-free raw-pipe checker, CI builds Core and runs the
documented inventory server with the official Python MCP SDK pinned separately to
`1.29.1` and `2.1.1`, on Linux, Windows and macOS with Python 3.11. The SDK is not a
Core runtime or development dependency: it is installed only in the client check
environment. The server receives only the exact Core wheel in a fresh offline
environment, runs outside the checkout with Python isolated mode, and must not
have the MCP SDK installed.

Use a separate client virtual environment, install `mcp==2.1.1`, then run from
the Core checkout using that environment's Python:

```bash
python -m pip install "mcp==2.1.1"
python -I scripts/verify_mcp_client.py /absolute/path/to/samsarix_core-2.0.0a9-py3-none-any.whl --sdk-version 2.1.1
```

Repeat in another client environment with both version arguments changed to
`1.29.1`. Omit the wheel path only when `dist/` contains exactly one wheel. The
checker rejects a mismatched SDK pin and reports the wheel SHA-256. Initial SDK
installation accesses the package index and installs that SDK's dependencies;
the subsequent Core installation is offline. SDK transitive dependencies are
resolved at installation time, not represented as a fully locked environment.

The journey uses official SDK transport/session methods and parsed models. It
checks initialization, ping, tool discovery and behavioral hints, Draft 2020-12
input/output schema validity, Unicode and escaped-newline calls, structured/text
agreement, safe validation errors, content-free client-filtered logging, correlated
progress, empty audit results, recovery after errors and client-context shutdown.
SDK 2.x uses its high-level client's default `auto` negotiation: it probes discovery
and falls back to the `2025-11-25` initialization handshake. Its session then runs
the shared tool journey; no modern protocol behavior is inferred from that fallback.

The same command then opens a separate official `ClientSession` against a controlled
in-memory cancellation fixture, using the same installed Core interpreter. It waits
for actual start progress, cancels the call, and invokes a state tool that needs the
same sole execution slot. Two consecutive cycles must show zero active/completed
waiters, exact tool/runtime cancellation counts, zero runtime timeouts, and only the
state tool's own in-flight/pending call. A successful ping follows each cycle.
Thus cancelling a local Python task without stopping server work cannot pass.
Execution capacity can become available before the cancelled invocation finishes
its terminal accounting. The checker allows only that exact transient (tool already
stopped, no timeouts/completions, at most one remaining cancelled admission) and
requires the exact final counters within the same five-second recovery deadline,
with at most 100 observations. Counter leakage still fails; retries do not cancel
the server work or replace cancellation with a timeout.

The tested paths deliberately differ:

| SDK pin | Cancellation path proved |
| --- | --- |
| `1.29.1` | Explicit typed SDK `notifications/cancelled`, then cancellation of the local waiting task. A forwarding observer reads the actual outgoing SDK request ID; it never guesses an ID, treats a progress token as an ID, or accesses SDK private counters. |
| `2.1.1` | Cancellation of the local waiting task triggers the SDK's automatic cancellation notification; the checker does not inject one. |

In SDK 1.29.1, cancelling a local waiter or hitting its read timeout does not itself
send a server cancellation notification. Hosts using that version must explicitly
notify the server if they need cooperative remote cancellation. This is client
behavior, not something Core can infer from a still-open stdio connection. The
checker prints the tested cancellation mode with its wheel digest.

The inventory session has a 45-second deadline; the cancellation session has a
20-second deadline with five-second start/recovery bounds. The outer checker has a 60-second
deadline and forcibly terminates the checker if SDK cleanup stalls. Because the SDK
may start its server in a separate process group, a stdlib-only test bootstrap also
enforces a 55-second server lifetime independently. The watchdog is cancelled on
normal exit; hard exit code 124 is a failed check, never graceful-shutdown evidence.
This bootstrap is only for the trusted example and controlled fixture, not production tools.
Setup commands also have finite timeouts. Negative-control unit tests reject wrong results, missing
progress, private log fields/values, SDK pin drift and checker failure, and exercise
timeout cleanup, including independent server exit. No model credentials, signed-in desktop UI or external API calls
are needed for the journey.

The default legacy gate does **not** validate experimental tasks, cancellation of synchronous or
non-cooperative functions, a signed-in tool-approval UI, HTTP/authentication, every
SDK version or newer MCP revisions. The explicit `--modern` mode above separately
covers the 2026 ordinary-tool path. Cancellation is not rollback of committed side
effects. The fixture performs no durable writes; Core's separate tests cover its
task and surviving-sync-worker contracts. SDK 2.x emits a logging deprecation
warning because the checker deliberately exercises the older negotiated revision.
Tasks in Core remain opt-in, revision-specific experimental behavior; the upstream
SDK removed its experimental task API in 2.x. Do not infer task compatibility from
ordinary tool-call success.

References checked on 2026-08-31: official SDK releases
[`v1.29.1`](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.29.1),
[`v2.1.1`](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.1.1),
the [2.x negotiation implementation](https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/client/_probe.py),
and the [2025-11-25 tool contract](https://modelcontextprotocol.io/specification/2025-11-25/server/tools).
Cancellation references: the [protocol requirements](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation),
[1.29.1 request handling](https://github.com/modelcontextprotocol/python-sdk/blob/v1.29.1/src/mcp/shared/session.py),
and [2.1.1 request abandonment](https://github.com/modelcontextprotocol/python-sdk/blob/v2.1.1/src/mcp/shared/jsonrpc_dispatcher.py).

## Declare behavior honestly

MCP clients use behavioral annotations to explain and gate tool calls. Samsarix
Core exposes them directly from `@samsarix_tool`:

```python
from samsarix_core import samsarix_tool


@samsarix_tool(
    title="Find an order",
    read_only=True,
    open_world=False,
)
def find_order(order_id: str) -> dict[str, str]:
    """Find one order in the application's local store."""

    return {"order_id": order_id, "status": "processing"}
```

The metadata has conservative defaults:

| Python option | MCP field | Default |
| --- | --- | --- |
| `read_only` | `readOnlyHint` | `False` |
| `destructive` | `destructiveHint` | `False` for read-only tools; otherwise `True` |
| `idempotent` | `idempotentHint` | `True` for read-only tools; otherwise `False` |
| `open_world` | `openWorldHint` | `True` |

Annotations are hints, not an authorization system. A client must not trust
annotations from an untrusted server, and an application must still enforce its
own identity, permissions, tenant boundaries, and human-approval policy.

## Apply a server-side policy without replacing client approval

An `MCPServer` uses its runtime's optional `policy` for ordinary and task-augmented
calls. The policy runs after argument validation and before the tool, and a denial is a
safe `isError: true` result with Samsarix status `denied`. It receives a detached call
snapshot that Core never adds to protocol output or operational logs.

This is a programmatic host gate, not MCP authorization or a confirmation prompt. The
MCP specification recommends that applications provide a human the ability to deny
tool invocations, so clients should continue to show and approve sensitive actions:
<https://modelcontextprotocol.io/specification/2025-11-25/server/tools>.

## Bound calls to quota-constrained tools

`ToolRuntime.register(..., rate_limit=ToolRateLimit(...))` applies the same process-local
token bucket to direct calls, ordinary MCP calls, and task-augmented calls. When no token
is available, an ordinary call returns `isError: true`, Samsarix status `rate_limited`,
safe code `tool_rate_limited`, and `details.retry_after_ms`. A task reaches `failed` and
`tasks/result` returns that same tool result. Core never reflects the call arguments in
the error.

The MCP tool security considerations require rate limiting, but this local bucket does
not identify clients or coordinate multiple server processes. A network adapter still
needs authenticated per-principal and distributed controls. See
[per-tool rate limits](RATE_LIMITS.md) for configuration and token-accounting semantics.

## Fail fast around an unhealthy dependency

`ToolRuntime.register(..., circuit_breaker=ToolCircuitBreaker(...))` applies the same
process-local breaker to direct, ordinary MCP, and task-augmented calls. An open circuit
returns `isError: true`, Samsarix status `circuit_open`, safe code
`tool_circuit_open`, and a retry delay when the recovery interval has time remaining.
The failure is a tool execution result rather than a JSON-RPC protocol error. A task
reaches `failed` and retains that exact safe result; call arguments and the triggering
exception are not reflected. See [per-tool circuit breakers](CIRCUIT_BREAKERS.md).

## Structured output

MCP requires an object at the root of `outputSchema`. Object-returning Samsarix
tools are exported directly. Scalar, array, tuple, union, and null outputs are
wrapped consistently:

```json
{
  "type": "object",
  "properties": {
    "result": { "type": "string" }
  },
  "required": ["result"],
  "additionalProperties": false
}
```

The corresponding successful `structuredContent` is `{"result": "..."}`.
For compatibility, the same data is serialized into a text content block.
Failures set `isError: true` and contain the safe `ToolError`; exception messages
remain redacted unless the runtime was explicitly created with
`expose_exceptions=True`.

## Progress

An async tool can publish bounded progress without adding a parameter to its
public schema:

```python
from samsarix_core import report_progress, samsarix_tool


async def index_one(record: str) -> None:
    """Replace this stub with application-owned async indexing."""

    return None


@samsarix_tool
async def index_records(records: list[str]) -> int:
    """Index records and report completed work."""

    for position, record in enumerate(records, start=1):
        await index_one(record)
        await report_progress(
            position,
            total=len(records),
            message=f"Indexed {position} of {len(records)} records",
        )
    return len(records)
```

The client opts in by adding a unique string or numeric token to the call:

```json
{
  "jsonrpc": "2.0",
  "id": "call-41",
  "method": "tools/call",
  "params": {
    "name": "index_records",
    "arguments": {"records": ["a", "b"]},
    "_meta": {"progressToken": "progress-41"}
  }
}
```

`serve_stdio()` writes each accepted `notifications/progress` message before the
terminal response. Progress values must be finite, non-negative, and strictly
increasing. `ToolRuntime` defaults to at most 1,000 accepted updates and 4,096
UTF-8 bytes per progress message for each invocation; tune
`max_progress_updates` and `max_progress_message_bytes` for the application.
Once the cap is reached, no handler exists, or the call has completed,
`report_progress()` returns `False`. Oversized transport notifications are
omitted instead of being replaced by a spurious JSON-RPC error.
A non-increasing progress value or an oversized progress message raises
`ValueError` and fails the tool invocation.

Progress is cooperative and currently available inside async tools. Messages are
sent to the client and may be displayed or logged, so do not include credentials,
document content, tenant identifiers, or other sensitive values. Core enforces
the MCP stable [progress utility](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/progress)
for normal and task-augmented calls. Task-owned progress includes the required
related-task metadata.

## Experimental task execution

MCP `2025-11-25` defines experimental task augmentation for expensive work and
batch processing. Samsarix Core supports the bounded local subset as an explicit
opt-in. Declare support on the individual tool and enable it on the server:

```python
@samsarix_tool(task_support="optional")
async def build_export(export_id: str) -> dict[str, str]:
    """Build one application-owned export."""

    return {"export_id": export_id, "status": "ready"}


runtime.register(build_export)
server = MCPServer(
    runtime,
    enable_tasks=True,
    max_retained_tasks=64,
    default_task_ttl_ms=300_000,
    max_task_ttl_ms=3_600_000,
    task_poll_interval_ms=500,
)
```

`task_support` is `"forbidden"` by default. `"optional"` allows either an
ordinary call or a task-augmented call, while `"required"` requires task
augmentation whenever `2025-11-25` task capabilities were negotiated. The setting
does not change direct `ToolRuntime` calls, and `2025-06-18` MCP clients retain
ordinary synchronous-response behavior.

A client creates a task by adding a task object to `tools/call`:

```json
{
  "jsonrpc": "2.0",
  "id": "create-export",
  "method": "tools/call",
  "params": {
    "name": "build_export",
    "arguments": {"export_id": "export-42"},
    "task": {"ttl": 60000}
  }
}
```

The immediate response contains a cryptographically random task ID and `working`
state, never the arguments or result. Poll `tasks/get`, retrieve the final
`CallToolResult` with `tasks/result`, or stop active work with `tasks/cancel`.
`tasks/result` waits until a terminal state but remains independently cancellable;
cancelling only that wait does not cancel the retained task. Every final result,
progress update, and operational event carries
`io.modelcontextprotocol/related-task` metadata.

Retention is in memory and scoped to one `MCPServer` session. Requested TTLs are
positive finite numbers representable as Python floats, then clamped to
`max_task_ttl_ms`. Expiry is checked when the store is accessed, including creation,
get, result, and cancellation; expired entries are removed and capacity reclaimed
then. A pending `tasks/result` wait is also bounded by its remaining TTL. Cleanup
is lazy: an idle server can retain expired result objects in memory until the next
store operation or server close. TTL is an access-validity limit, not a timed memory
erasure guarantee. Arguments must pass the runtime's byte, depth, node, cycle, and JSON
compatibility preflight before the server detaches them for background execution.
At `max_retained_tasks`, new task requests receive server-busy error `-32000`.
Task cancellation is cooperative: async work is cancelled, while a running
synchronous function can retain its runtime worker until it actually stops.
Invalid requested TTLs, including overflowing integers, receive invalid-parameters
error `-32602` before task creation, leaving retention capacity available. Host
duration settings (`default_task_ttl_ms`, `max_task_ttl_ms`, `task_poll_interval_ms`)
must be positive integers representable as finite floats.

Core deliberately does not advertise `tasks.list` on unauthenticated stdio. MCP's
task security guidance warns that listing can expose task metadata when requestor
identity cannot be bound. Random IDs make guessing impractical, but any process
with a valid task ID on the same logical session can retrieve or cancel it. A
network host must bind task access to authenticated authorization context, add
per-principal quotas and rate limits, and should provide a separate persistent
task store before claiming durable service behavior. See the experimental
[MCP Tasks specification](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/tasks).

## Operational logging

Enable the stable MCP logging capability when a client needs runtime health events:

```python
server = MCPServer(
    runtime,
    enable_logging=True,
    default_log_level="warning",
)
```

The client can select any syslog-compatible MCP minimum level with
`logging/setLevel`: `debug`, `info`, `notice`, `warning`, `error`, `critical`,
`alert`, or `emergency`. Core emits at most one `notifications/message` event for
each non-cancelled tool call: successful results use `info` and failures use
`error`. The default `warning` threshold therefore suppresses successful-call
events until the client requests `info` or `debug`.

Each event contains only the already-public tool name, invocation ID, terminal
status, and duration. Core never copies arguments, outputs, exception text,
validation details, cancellation reasons, or progress messages into operational
logs. Delivery is best effort: a failing log notification sender does not replace
an already-computed tool result. `serve_stdio()` serializes an accepted log before
the terminal response and drops an oversized notification with a generic stderr
diagnostic.

Logging is disabled by default, is advertised only when enabled, and remains
bounded to one event per call. A network host still needs connection-level rate
limits and access control. This implements the stable MCP
[logging utility](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/logging)
with a deliberately content-free data shape.

## Request cancellation and admission

MCP clients can stop an active ordinary call or a blocking `tasks/result` wait
with a notification:

```json
{
  "jsonrpc": "2.0",
  "method": "notifications/cancelled",
  "params": {
    "requestId": "call-42",
    "reason": "User stopped the operation"
  }
}
```

Core cancels the matching request and sends no response for it, as required by
MCP. Cancelling a `tasks/result` wait leaves the retained task running; use
`tasks/cancel` to transition the task itself to `cancelled`. Unknown, completed,
missing, or malformed request IDs are ignored. Cancellation reasons are not
logged by Core. Host cancellation of the `handle()` coroutine still propagates
as `asyncio.CancelledError`; it is not mistaken for an MCP client notification.

`serve_stdio()` reads control messages while tool calls are active and serializes
all responses through one writer lock. It admits at most
`max_in_flight_requests=64` tool-call or task-result coroutines by default. This
admission cap is
separate from `ToolRuntime.max_concurrency`: the former bounds waiting protocol
requests, while the latter bounds executing tools. Excess calls receive JSON-RPC
server error `-32000` and are not executed. Normal input EOF drains calls that
were already admitted.

Async cancellation is cooperative. A synchronous Python function cannot be
force-stopped; cancelling its MCP request stops the protocol wait while the
runtime retains its real worker and concurrency slot until the function exits.
This follows MCP's stable
[cancellation utility](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)
and the experimental task cancellation state transition.

## Embed without stdio

Applications with an existing transport can call the protocol handler directly:

```python
server = MCPServer(runtime)
response = await server.handle(
    json_rpc_message,
    notification_sender=send_json_rpc_notification,
)
```

`handle()` accepts one parsed JSON-RPC object and returns a response object or
`None` for notifications and MCP-cancelled calls. The optional async sender is
required for progress and operational-log delivery. An `MCPServer` instance is one
logical MCP connection/session; create separate instances for independently
negotiated clients. A custom concurrent transport must serialize its
outbound messages and deliver cancellation notifications while the corresponding
`handle()` call is still active. HTTP authentication, MCP session headers, origin
validation, request body limits, and rate limits must be implemented by the
hosting HTTP layer.

Call `await server.aclose()` to cancel retained background tasks and close the
runtime. Pass `close_runtime=False` only when the application owns the runtime's
later shutdown. `serve_stdio()` performs the default server close at transport
shutdown unless its own `close_runtime=False` option transfers that responsibility
to the host.

A notification-sender failure while delivering requested progress for an ordinary
call raises `ProgressHandlerError` with the original transport exception chained
as its cause; it is not converted into an `isError` tool result. A task has already
returned its creation response, so the same background delivery failure instead
makes that retained task fail with a generic safe result. Operational-log delivery
is separately best effort, so its sender failures are suppressed and the
already-computed tool result remains unchanged.

## Operational boundaries

- Registered functions remain trusted in-process application code.
- Read-only and idempotent annotations do not make a function safe by themselves.
- `serve_stdio()` caps individual requests and responses at 1 MiB by default.
- `serve_stdio()` admits at most 64 active tool-call or task-result requests by
  default; tune the cap with `max_in_flight_requests`.
- Runtime timeouts and concurrency controls continue to apply to MCP calls.
- Host-policy evaluation is bounded, included in invocation timeout/cancellation, and
  precedes any tool progress or side effect.
- Progress is opt-in, strictly increasing, update-capped, message-bounded, and
  automatically closed before a call's terminal response.
- Progress messages cross the protocol boundary; keep them free of sensitive data.
- Client cancellation emits no response, stops cooperative async tools, and does
  not imply a running sync function has stopped.
- A timed-out synchronous function retains its bounded worker slot until it stops.
- Experimental tasks are disabled by default, retained only in memory, and capped
  at 64 entries by default. Access expires within the configured TTL (one-hour
  maximum by default); idle in-memory cleanup is lazy, not a timed erasure guarantee.
- `tasks.list` is not exposed without requestor identity; possession of a valid
  task ID permits get, result, and cancellation within the same server session.
- `serve_stdio()` closes without waiting indefinitely for surviving sync work. A
  host that requires shutdown quiescence should set `close_runtime=False`, stop
  MCP admission, and call
  `runtime.aclose(wait_for_sync=True, timeout=<deadline>)` itself.
- Tool arguments and results are not logged by the bridge.
- Keep user confirmation in the MCP host for write, destructive, and open-world
  calls.
