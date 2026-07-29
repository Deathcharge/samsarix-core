# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Offline end-to-end example for the supported Samsarix Core workflow."""

from __future__ import annotations

import asyncio
import json
from typing import Literal

from samsarix_core import ToolCall, ToolRuntime, samsarix_tool


@samsarix_tool(timeout=2, tags=("example", "math"))
def calculate(left: float, operation: Literal["add", "multiply"], right: float) -> float:
    """Apply one safe arithmetic operation to two numbers."""

    return left + right if operation == "add" else left * right


async def main() -> None:
    async with ToolRuntime(max_concurrency=2) as runtime:
        runtime.register(calculate)

        print("Contract:")
        print(json.dumps(runtime.registry.schema_catalog(), indent=2))

        calls = [
            ToolCall("calculate", {"left": 2, "operation": "add", "right": 3}),
            ToolCall("calculate", {"left": 4, "operation": "multiply", "right": 5}),
            ToolCall("calculate", {"left": 1, "operation": "divide", "right": 2}),
        ]
        print("\nResults:")
        for result in await runtime.invoke_many(calls):
            print(json.dumps(result.to_dict(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())
