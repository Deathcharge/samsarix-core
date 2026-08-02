# API reference

This page describes the complete supported API for `2.0.0a1`. Imports not exposed
from `samsarix_core.__all__` are internal.

## `samsarix_tool`

```python
@samsarix_tool(
    name: str | None = None,
    description: str | None = None,
    timeout: float | None = None,
    version: str = "1",
    tags: tuple[str, ...] = (),
    title: str | None = None,
    read_only: bool = False,
    destructive: bool | None = None,
    idempotent: bool | None = None,
    open_world: bool = True,
)
```

Works as `@samsarix_tool` or `@samsarix_tool(...)` on standalone sync and async functions.
Names use `[A-Za-z][A-Za-z0-9_-]{0,63}`. Descriptions fall back to the first
docstring line. Unsupported types, unresolved annotations, generators, positional-
only parameters, `*args`, and `**kwargs` raise `ToolDefinitionError`.
The final five options produce MCP display and behavioral annotations. Read-only
tools infer `destructive=False` and `idempotent=True`; other tools retain MCP's
conservative destructive/non-idempotent defaults unless explicitly annotated.

## `ToolRegistry`

```python
ToolRegistry(*, max_tools: int = 256)
```

- `register(function, *, replace=False) -> ToolSpec`
- `unregister(name) -> ToolSpec`
- `get(name) -> ToolSpec`
- `list() -> tuple[ToolSpec, ...]`
- `schema_catalog() -> dict`

Duplicate registration raises `DuplicateToolError` unless replacement is explicit.
Adding a new tool at capacity raises `RegistryCapacityError`; replacing an existing
tool remains allowed. Unknown direct lookups/removals raise `ToolNotFoundError`.
Runtime lookup failures become structured results instead.

## `ToolRuntime`

```python
ToolRuntime(
    registry: ToolRegistry | None = None,
    *,
    max_concurrency: int = 8,
    max_batch_size: int = 256,
    max_argument_bytes: int = 1_048_576,
    max_output_bytes: int = 1_048_576,
    max_value_depth: int = 32,
    max_value_nodes: int = 10_000,
    max_progress_updates: int = 1_000,
    max_progress_message_bytes: int = 4_096,
    default_timeout: float = 30.0,
    expose_exceptions: bool = False,
)
```

- `register(function, *, replace=False) -> ToolSpec`
- `await invoke(name, arguments=None, *, timeout=None, progress_handler=None) -> ToolResult`
- `await invoke_many(calls) -> list[ToolResult]`
- `metrics() -> RuntimeMetrics`
- `pending_sync_calls -> int`
- `await wait_for_sync(*, timeout=None) -> bool`
- `await aclose(*, wait_for_sync=False, timeout=None) -> bool`

Timeout precedence is invocation override, decorator timeout, then runtime default.
The timeout includes time waiting for a concurrency slot. Batch results preserve
order. A batch larger than `max_batch_size` raises `ValueError` before any call is
started. `aclose()` is idempotent.

Argument and output sizes are the UTF-8 byte length of compact JSON. The root is
depth zero; every child increments depth. Each container and scalar is one node,
while object keys are covered by the byte limit but do not count as nodes. Cyclic,
oversized, over-depth, and over-node arguments return `invalid_arguments` without
executing the tool. Output resource violations return `failed` with the safe error
code `output_limit_exceeded`. All integer limits must be positive and reject booleans.

A timed-out or caller-cancelled sync callable cannot be killed safely. It remains
in `pending_sync_calls`, keeps its semaphore slot, and remains included in
`metrics().in_flight` until the underlying thread actually stops. This prevents
timeouts from feeding an unbounded executor queue. Late exceptions are consumed
without being exposed through the event loop.

`wait_for_sync()` snapshots currently submitted sync calls and returns `False` if
its optional non-negative timeout expires. For a race-free shutdown sequence, stop
external admission or close the runtime first. `aclose()` rejects new calls,
cancels active async waits, cancels sync work that has not started, and returns
whether submitted sync work is quiescent. Its default does not wait; pass
`wait_for_sync=True` with a finite timeout when shutdown needs bounded quiescence.
Calling it again is safe. The async context manager uses the non-waiting default.

`progress_handler` is an optional sync or async callable receiving immutable
`ToolProgress` values. An asynchronous tool reports through
`await report_progress(progress, total=None, message=None)`. Updates must use
finite non-negative numbers and strictly increase. The helper returns `False`
when no handler is active, the invocation is complete, or the configured update
cap is exhausted. Progress messages are UTF-8 bounded separately and may contain
sensitive application text, so tools should keep them generic. Synchronous tools
do not have an async reporting context.

## `MCPServer`

```python
MCPServer(
    runtime: ToolRuntime,
    *,
    name: str = "samsarix-core",
    title: str = "Samsarix Core",
    version: str = __version__,
    instructions: str | None = None,
)
```

- `await handle(message, *, notification_sender=None) -> dict | None`

`handle()` accepts one parsed MCP JSON-RPC message. It supports lifecycle
initialization, `ping`, `tools/list`, `tools/call`, initialized notifications, and
`notifications/cancelled` for active calls. A request with
`_meta.progressToken` can receive `notifications/progress` through the optional
async `notification_sender`; duplicate active tokens are rejected. It negotiates
MCP `2025-11-25` and `2025-06-18`. Application-level tool failures are successful
JSON-RPC responses with `isError: true`; malformed protocol calls use standard
JSON-RPC error objects. An MCP-cancelled call returns `None` and emits no response.
Direct host task cancellation continues to raise `asyncio.CancelledError`.

## `serve_stdio`

```python
await serve_stdio(
    server: MCPServer,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    max_message_bytes: int = 1_048_576,
    max_in_flight_requests: int = 64,
    close_runtime: bool = True,
)
```

Runs the server using newline-delimited MCP messages. `max_message_bytes` must be
at least 256 and caps individual input and output messages. Tool calls are
dispatched concurrently so cancellation notifications remain responsive, with
pending calls bounded separately by the positive `max_in_flight_requests` cap.
Excess calls receive JSON-RPC server error `-32000`. The default streams are
binary stdin and UTF-8 binary stdout. Only protocol messages are written to
stdout.

## Data models

All public models are frozen, slotted dataclasses.

- `ToolSpec`: name, description, input/output schemas, timeout, version, tags,
  async state, optional title, and read-only/destructive/idempotent/open-world hints.
- `ToolCall`: name, arguments, and optional timeout override.
- `ToolResult`: invocation ID, tool name, status, UTC start time, duration, output,
  and optional structured error. `success` is a convenience property.
- `ToolError`: code, safe message, optional exception type/details, and retryable flag.
- `ToolProgress`: numeric progress, optional total, and optional human-readable message.
- `RuntimeMetrics`: content-free counters only.
- `ToolStatus`: `success`, `not_found`, `invalid_arguments`, `timed_out`, `failed`,
  and `runtime_closed`.

`ToolSpec`, `ToolResult`, `ToolError`, and `RuntimeMetrics` provide `to_dict()`.

## Supported annotations

- scalars: `str`, `bool`, `int`, `float`, `None`
- `Literal` with JSON-scalar values
- unions and `Optional`
- `list[T]`
- fixed `tuple[T1, T2]` and variable `tuple[T, ...]`
- `dict[str, T]`
- `TypedDict` with strict named fields, nesting, inheritance, and total/optional
  key semantics
- `Annotated[T, "property description"]`

`Required` and `NotRequired` are honored when their provider (`typing` on Python
3.11+ or an application-installed compatible backport) is available. Recursive
`TypedDict` definitions are rejected during tool declaration so schema generation
cannot recurse indefinitely. Tool invocations still pass and return ordinary
dictionaries; Core does not construct user-defined objects.

`Any`, dataclasses, enums, custom classes, sets, arbitrary mappings, bytes,
datetimes, and non-string dictionary keys are intentionally not part of the alpha
contract. Integers do not accept booleans. Floats must be finite. Defaults and
outputs are checked too.

## Exceptions

Public definition/registry exceptions are `SamsarixError`, `ToolDefinitionError`,
`DuplicateToolError`, `RegistryCapacityError`, and `ToolNotFoundError`. A host
progress callback failure raises `ProgressHandlerError` with the original failure
as its cause instead of misclassifying it as a tool result. Ordinary invocation
failures are returned as `ToolResult`. `asyncio.CancelledError` propagates.

`helix_core`, `helix_tool`, and `HelixError` are compatibility aliases for the
pre-rebrand alpha surface. They are not the preferred names for new code.
