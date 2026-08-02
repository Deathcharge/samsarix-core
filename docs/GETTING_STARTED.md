# Getting started

## 1. Install

Use Python 3.10 or newer from the repository root:

```bash
python -m pip install .
```

For an editable development install:

```bash
python -m pip install -e ".[dev]"
```

## 2. Declare a tool

```python
from samsarix_core import samsarix_tool


@samsarix_tool(timeout=5, version="1")
def greet(name: str, excited: bool = False) -> str:
    """Build a greeting for one person."""

    suffix = "!" if excited else "."
    return f"Hello, {name}{suffix}"
```

Tool definitions are checked when Python evaluates the decorator. All parameters
and the return value must use the supported JSON-compatible type subset.

Use `TypedDict` when each object field has a different type and should appear by
name in JSON Schema:

```python
from typing import TypedDict


class Greeting(TypedDict):
    message: str
    excited: bool


@samsarix_tool
def structured_greeting(name: str, excited: bool = False) -> Greeting:
    """Build a structured greeting."""

    suffix = "!" if excited else "."
    return {"message": f"Hello, {name}{suffix}", "excited": excited}
```

Unlike `dict[str, str | bool]`, this produces individual `message` and `excited`
properties, requires both keys, and rejects additional output keys.

## 3. Register, inspect, and invoke

```python
import asyncio
import json

from samsarix_core import ToolRuntime


async def main() -> None:
    async with ToolRuntime() as runtime:
        spec = runtime.register(greet)
        print(json.dumps(spec.to_dict(), indent=2))

        result = await runtime.invoke("greet", {"name": "Ada", "excited": True})
        if result.success:
            print(result.output)
        else:
            print(result.error.to_dict() if result.error else "unknown error")


asyncio.run(main())
```

`runtime.registry.schema_catalog()` returns all registered contracts in stable
name order. Catalog data and results are detached JSON-compatible objects.

## 4. Invoke a bounded batch

```python
from samsarix_core import ToolCall

calls = [ToolCall("greet", {"name": name}) for name in ("Ada", "Grace", "Linus")]
results = await runtime.invoke_many(calls)
```

Results keep input order. The runtime creates at most `max_pending_invocations` batch
workers so calls queued on one per-tool bulkhead do not block unrelated tools; global
and per-tool limits still bound execution, and sync functions share a thread pool of
`max_concurrency` workers.

## 5. Add a host policy when calls need central admission control

```python
from samsarix_core import ToolPolicyContext, ToolPolicyDecision, ToolRuntime


async def read_only_policy(context: ToolPolicyContext) -> ToolPolicyDecision:
    return (
        ToolPolicyDecision.ALLOW
        if context.spec.read_only
        else ToolPolicyDecision.DENY
    )


runtime = ToolRuntime(policy=read_only_policy)
```

The policy runs only for resolved calls with valid, resource-bounded arguments. Its
snapshot is detached from execution, but may contain sensitive input. A denial returns
a normal structured result without running tool code. See
[`examples/policy_gate.py`](../examples/policy_gate.py) for request-local scopes.

## 6. Add content-free lifecycle signals when needed

```python
from collections import deque

from samsarix_core import ToolLifecycleEvent, ToolRuntime

recent_events: deque[ToolLifecycleEvent] = deque(maxlen=1_024)
runtime = ToolRuntime(lifecycle_handler=recent_events.append)
```

The synchronous callback receives paired start and terminal events but no arguments,
outputs, or exception text. This bounded in-memory diagnostic buffer deliberately drops
its oldest event at capacity. For durable telemetry, keep the callback non-blocking and
hand off to a bounded application-owned processor with an explicit drop or backpressure
policy. See the [lifecycle observability guide](OBSERVABILITY.md) for privacy,
cancellation, and OpenTelemetry semantics.

## 7. Handle boundaries explicitly

- Use `async with` or call `await runtime.aclose()`.
- Treat tool functions as trusted in-process code.
- Add I/O timeouts inside sync tools; the runtime cannot terminate Python threads.
- Leave exception exposure disabled outside a trusted developer environment.
- Check `result.status` or `result.success`; caller cancellation still propagates.
- Treat host policy as defense in depth, not authentication or a persistent
  human-approval system.
