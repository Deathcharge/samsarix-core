# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Repeatable, dependency-free Samsarix Core MCP stdio microbenchmark."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import platform
import time
from typing import Any

from samsarix_core import (
    MCPServer,
    ToolRuntime,
    __version__,
    report_progress,
    samsarix_tool,
    serve_stdio,
)


@samsarix_tool(read_only=True)
async def increment(value: int, progress_updates: int = 0) -> int:
    """Increment an integer."""

    for update in range(1, progress_updates + 1):
        await report_progress(update, total=progress_updates)
    return value + 1


async def benchmark(
    iterations: int,
    max_concurrency: int,
    max_in_flight_requests: int,
    progress_updates_per_call: int,
) -> dict[str, Any]:
    """Measure the complete in-memory MCP stdio tool-call path."""

    initialize = {
        "jsonrpc": "2.0",
        "id": "initialize",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "stdio-benchmark", "version": "1"},
        },
    }
    messages = [initialize, {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    for index in range(iterations):
        params: dict[str, Any] = {
            "name": "increment",
            "arguments": {
                "value": index,
                "progress_updates": progress_updates_per_call,
            },
        }
        if progress_updates_per_call:
            params["_meta"] = {"progressToken": f"progress-{index}"}
        messages.append(
            {
                "jsonrpc": "2.0",
                "id": index,
                "method": "tools/call",
                "params": params,
            }
        )
    payload = ("\n".join(json.dumps(message) for message in messages) + "\n").encode()
    output = io.StringIO()
    runtime = ToolRuntime(max_concurrency=max_concurrency)
    runtime.register(increment)

    started = time.perf_counter()
    await serve_stdio(
        MCPServer(runtime),
        input_stream=io.BytesIO(payload),
        output_stream=output,
        max_in_flight_requests=max_in_flight_requests,
    )
    elapsed = time.perf_counter() - started

    responses = [json.loads(line) for line in output.getvalue().splitlines()]
    tool_responses = {
        response["id"]: response
        for response in responses
        if "id" in response and response["id"] != "initialize"
    }
    progress_notifications = [
        response for response in responses if response.get("method") == "notifications/progress"
    ]
    if len(tool_responses) != iterations:
        raise RuntimeError("benchmark did not receive one response per tool call")
    for index in range(iterations):
        response = tool_responses[index]
        if response.get("result", {}).get("structuredContent") != {"result": index + 1}:
            raise RuntimeError("benchmark received an invalid or failed tool response")
    expected_progress = iterations * progress_updates_per_call
    if len(progress_notifications) != expected_progress:
        raise RuntimeError("benchmark did not receive the expected progress notifications")
    progress_by_token: dict[str, list[float]] = {}
    for notification in progress_notifications:
        params = notification.get("params")
        if not isinstance(params, dict):
            raise RuntimeError("benchmark received malformed progress parameters")
        token = params.get("progressToken")
        progress = params.get("progress")
        total = params.get("total")
        if not isinstance(token, str) or not isinstance(progress, (int, float)):
            raise RuntimeError("benchmark received malformed progress values")
        if total != float(progress_updates_per_call):
            raise RuntimeError("benchmark received an invalid progress total")
        progress_by_token.setdefault(token, []).append(float(progress))
    expected_values = [float(value) for value in range(1, progress_updates_per_call + 1)]
    for index in range(iterations):
        token = f"progress-{index}"
        if progress_by_token.get(token, []) != expected_values:
            raise RuntimeError("benchmark received an invalid progress sequence")

    return {
        "environment": {
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "samsarix_core": __version__,
        },
        "settings": {
            "iterations": iterations,
            "max_concurrency": max_concurrency,
            "max_in_flight_requests": max_in_flight_requests,
            "progress_updates_per_call": progress_updates_per_call,
        },
        "stdio_tool_calls": {
            "calls_per_second": round(iterations / elapsed, 2),
            "duration_ms": round(elapsed * 1_000, 4),
        },
        "progress_notifications": {
            "count": len(progress_notifications),
            "notifications_per_second": round(len(progress_notifications) / elapsed, 2),
        },
    }


def positive_integer(value: str) -> int:
    """Parse one positive command-line integer."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def non_negative_integer(value: str) -> int:
    """Parse one non-negative command-line integer."""

    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("value must be non-negative")
    return parsed


def main() -> None:
    """Run the benchmark and print machine-readable JSON."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=positive_integer, default=2_000)
    parser.add_argument("--max-concurrency", type=positive_integer, default=8)
    parser.add_argument("--max-in-flight-requests", type=positive_integer, default=64)
    parser.add_argument(
        "--progress-updates-per-call",
        type=non_negative_integer,
        default=0,
    )
    arguments = parser.parse_args()
    report = asyncio.run(
        benchmark(
            arguments.iterations,
            arguments.max_concurrency,
            arguments.max_in_flight_requests,
            arguments.progress_updates_per_call,
        )
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
