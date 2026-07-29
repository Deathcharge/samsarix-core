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

Results keep input order. The runtime creates at most `max_concurrency` workers,
and sync functions share a thread pool of the same maximum size.

## 5. Handle boundaries explicitly

- Use `async with` or call `await runtime.aclose()`.
- Treat tool functions as trusted in-process code.
- Add I/O timeouts inside sync tools; the runtime cannot terminate Python threads.
- Leave exception exposure disabled outside a trusted developer environment.
- Check `result.status` or `result.success`; caller cancellation still propagates.
