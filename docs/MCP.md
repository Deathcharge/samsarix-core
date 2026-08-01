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
- newline-delimited stdio with a configurable message-size cap.

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

## Embed without stdio

Applications with an existing transport can call the protocol handler directly:

```python
server = MCPServer(runtime)
response = await server.handle(json_rpc_message)
```

`handle()` accepts one parsed JSON-RPC object and returns a response object or
`None` for notifications. HTTP authentication, MCP session headers, origin
validation, request body limits, and rate limits must be implemented by the
hosting HTTP layer.

## Operational boundaries

- Registered functions remain trusted in-process application code.
- Read-only and idempotent annotations do not make a function safe by themselves.
- `serve_stdio()` caps individual requests and responses at 1 MiB by default.
- Runtime timeouts and concurrency controls continue to apply to MCP calls.
- A timed-out synchronous function may continue in its bounded worker thread.
- Tool arguments and results are not logged by the bridge.
- Keep user confirmation in the MCP host for write, destructive, and open-world
  calls.
