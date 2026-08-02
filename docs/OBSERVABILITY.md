# Lifecycle observability

Samsarix Core can emit an opt-in, provider-neutral lifecycle signal before and after
every attempted invocation. The signal is designed for traces, service-level
indicators, structured operational logs, and test probes without copying tool
arguments, outputs, exception messages, policy context, or progress text.

```python
from samsarix_core import ToolLifecycleEvent, ToolRuntime


def observe(event: ToolLifecycleEvent) -> None:
    print(event.to_dict())


runtime = ToolRuntime(lifecycle_handler=observe)
```

The handler receives one immutable `started` event followed by exactly one terminal
event for every ordinary invocation path. Returned `ToolResult` states keep their
existing names. Caller cancellation produces `cancelled`; an exception that crosses
the runtime boundary, such as a failing progress transport or invalid host callback,
produces `aborted`. Start events have `duration_ms=None`; terminal duration uses the
same monotonic measurement as `ToolResult`. Both events share the invocation ID and
requested tool name.

The event contains only:

- `invocation_id`;
- `tool_name`;
- lifecycle `status`;
- UTC `occurred_at`; and
- logical `duration_ms` on terminal events.

This is content-free, not identity-free. Tool names reveal application structure,
invocation IDs are correlatable, and the name on a `not_found` attempt can be
attacker-controlled. Opt in only at a trusted host boundary. Apply an allowlist before
using names as metric labels, and configure retention and access controls in the
telemetry backend.

## Handler isolation and backpressure

`lifecycle_handler` must be a synchronous callable. Core invokes it inline, so keep it
constant-time and non-blocking. Ordinary handler exceptions and accidental awaitable
returns are swallowed, counted in `RuntimeMetrics.lifecycle_handler_failures`, and do
not replace a tool result or cancellation. Async callables are rejected when the
runtime is constructed.

Core deliberately does not create an unbounded telemetry queue, thread, or task. Send
network telemetry through a bounded or batched processor owned by the application.
OpenTelemetry, for example, recommends batching exporters. A callback that performs
network I/O directly can add latency even though its ordinary failures are isolated.

The lifecycle duration represents the caller-visible logical attempt. A synchronous
function cannot be force-stopped: after timeout or cancellation its terminal event can
occur while the worker thread is still running. Use `pending_sync_calls`,
`metrics().in_flight`, and bounded shutdown quiescence to observe that physical
lifetime.

## OpenTelemetry adapter

OpenTelemetry's developing GenAI semantic conventions define an internal
`execute_tool` span named `execute_tool {gen_ai.tool.name}`. Tool arguments and results
are opt-in attributes because they can contain sensitive data. The following
application-owned adapter intentionally omits both content attributes:

```python
from threading import Lock

from opentelemetry import trace
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from samsarix_core import ToolLifecycleEvent, ToolLifecycleStatus, ToolRuntime

tracer = trace.get_tracer("my-service.samsarix")
spans: dict[str, Span] = {}
spans_lock = Lock()


def observe(event: ToolLifecycleEvent) -> None:
    if event.status is ToolLifecycleStatus.STARTED:
        span = tracer.start_span(
            f"execute_tool {event.tool_name}",
            kind=SpanKind.INTERNAL,
            attributes={
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": event.tool_name,
                "gen_ai.tool.type": "function",
                "gen_ai.tool.call.id": event.invocation_id,
            },
        )
        with spans_lock:
            spans[event.invocation_id] = span
        return

    with spans_lock:
        span = spans.pop(event.invocation_id, None)
    if span is None:
        return

    span.set_attribute("samsarix.tool.status", event.status.value)
    if event.status is not ToolLifecycleStatus.SUCCESS:
        span.set_attribute("error.type", f"samsarix.{event.status.value}")
        span.set_status(Status(StatusCode.ERROR))
    span.end()


runtime = ToolRuntime(lifecycle_handler=observe)
```

The host installs the OpenTelemetry API, SDK, processor, and exporter; Samsarix Core
keeps no OpenTelemetry runtime dependency. Prefer a batch span processor, bound the
export path, and treat the GenAI convention as development-stage until OpenTelemetry
declares it stable.

Primary references:

- [OpenTelemetry GenAI `execute_tool` span definition](https://github.com/open-telemetry/semantic-conventions-genai/blob/main/model/gen-ai/spans.yaml)
- [OpenTelemetry Python instrumentation guidance](https://opentelemetry.io/docs/languages/python/instrumentation/)
- [OpenTelemetry Python exporter and batching guidance](https://opentelemetry.io/docs/languages/python/exporters/)
- [MCP logging utility](https://modelcontextprotocol.io/specification/2025-11-25/server/utilities/logging)

## Choosing a signal

| Need | Core surface | Cardinality/content |
| --- | --- | --- |
| Aggregate runtime health | `RuntimeMetrics` | Content-free counters; no tool names |
| Per-invocation traces or host logs | `lifecycle_handler` | Tool name and invocation ID; no call content |
| MCP client diagnostics | opt-in MCP logging | Terminal tool name, ID, status, and duration |
| User-facing work progress | `progress_handler` | Application text may cross the trust boundary |

Avoid enabling two terminal logging paths into the same backend unless duplicate
events are intentional. Lifecycle signals operate at the direct runtime boundary and
therefore cover direct, batch, MCP, and task-augmented calls uniformly.
