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
  structured errors;
- requested `notifications/progress` updates from cooperative asynchronous tools;
- `notifications/cancelled` for active non-task tool calls;
- newline-delimited stdio with configurable message-size and active-request caps.

It does not implement MCP resources, prompts, sampling, tasks, HTTP transport,
authentication, or authorization. Those remain host-application concerns.

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
without adopting experimental Tasks.

## Cancellation and admission

MCP clients can stop an active non-task call with a notification:

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

Core cancels the matching async request and sends no response for the cancelled
call, as required by MCP. Unknown, completed, missing, or malformed request IDs
are ignored. Cancellation reasons are not logged by Core. Host cancellation of
the `handle()` coroutine still propagates as `asyncio.CancelledError`; it is not
mistaken for an MCP client notification.

`serve_stdio()` reads control messages while tool calls are active and serializes
all responses through one writer lock. It admits at most
`max_in_flight_requests=64` tool-call coroutines by default. This admission cap is
separate from `ToolRuntime.max_concurrency`: the former bounds waiting protocol
requests, while the latter bounds executing tools. Excess calls receive JSON-RPC
server error `-32000` and are not executed. Normal input EOF drains calls that
were already admitted.

Async cancellation is cooperative. A synchronous Python function cannot be
force-stopped; cancelling its MCP request stops the protocol wait while the
runtime retains its real worker and concurrency slot until the function exits.
This follows MCP's stable
[cancellation utility](https://modelcontextprotocol.io/specification/2025-11-25/basic/utilities/cancellation)
without adopting the separate experimental Tasks surface.

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
required for progress delivery. A custom concurrent transport must serialize its
outbound messages and deliver cancellation notifications while the corresponding
`handle()` call is still active. HTTP authentication, MCP session headers, origin
validation, request body limits, and rate limits must be implemented by the
hosting HTTP layer.

A failing notification sender raises `ProgressHandlerError` with the original
transport exception chained as its cause. It is not converted into an `isError`
tool result.

## Operational boundaries

- Registered functions remain trusted in-process application code.
- Read-only and idempotent annotations do not make a function safe by themselves.
- `serve_stdio()` caps individual requests and responses at 1 MiB by default.
- `serve_stdio()` admits at most 64 active tool-call requests by default; tune the
  cap with `max_in_flight_requests`.
- Runtime timeouts and concurrency controls continue to apply to MCP calls.
- Progress is opt-in, strictly increasing, update-capped, message-bounded, and
  automatically closed before a call's terminal response.
- Progress messages cross the protocol boundary; keep them free of sensitive data.
- Client cancellation emits no response, stops cooperative async tools, and does
  not imply a running sync function has stopped.
- A timed-out synchronous function retains its bounded worker slot until it stops.
- `serve_stdio()` closes without waiting indefinitely for surviving sync work. A
  host that requires shutdown quiescence should set `close_runtime=False`, stop
  MCP admission, and call
  `runtime.aclose(wait_for_sync=True, timeout=<deadline>)` itself.
- Tool arguments and results are not logged by the bridge.
- Keep user confirmation in the MCP host for write, destructive, and open-world
  calls.
