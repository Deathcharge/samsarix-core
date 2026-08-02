# Model Context Protocol bridge

Samsarix Core can expose its trusted local tools through the Model Context
Protocol (MCP) without adding a runtime dependency. The bridge targets the
current stable MCP protocol version, `2025-11-25`, and also negotiates
`2025-06-18` clients.

The supported server surface is intentionally narrow:

- lifecycle initialization and version negotiation;
- `ping`;
- `tools/list` with JSON Schema Draft 2020-12 input and output contracts;
- `tools/call` with Samsarix validation, timeouts, concurrency limits, and safe
  structured errors, including optional host-policy denial;
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
clamped to `max_task_ttl_ms`; expired tasks and results are removed, and capacity
is reclaimed. Arguments must pass the runtime's byte, depth, node, cycle, and JSON
compatibility preflight before the server detaches them for background execution.
At `max_retained_tasks`, new task requests receive server-busy error `-32000`.
Task cancellation is cooperative: async work is cancelled, while a running
synchronous function can retain its runtime worker until it actually stops.

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
- Experimental tasks are disabled by default, retained only in memory, capped at
  64 entries by default, and expire no later than the configured one-hour maximum.
- `tasks.list` is not exposed without requestor identity; possession of a valid
  task ID permits get, result, and cancellation within the same server session.
- `serve_stdio()` closes without waiting indefinitely for surviving sync work. A
  host that requires shutdown quiescence should set `close_runtime=False`, stop
  MCP admission, and call
  `runtime.aclose(wait_for_sync=True, timeout=<deadline>)` itself.
- Tool arguments and results are not logged by the bridge.
- Keep user confirmation in the MCP host for write, destructive, and open-world
  calls.
