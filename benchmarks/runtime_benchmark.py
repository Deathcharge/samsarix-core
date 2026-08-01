# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Repeatable, dependency-free Samsarix Core runtime microbenchmark."""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import platform
import statistics
import time
from typing import Any

from samsarix_core import ToolCall, ToolRuntime, __version__, samsarix_tool


@samsarix_tool(read_only=True)
async def increment(value: int) -> int:
    """Increment an integer."""

    return value + 1


@samsarix_tool(name="increment_sync", read_only=True)
def increment_sync(value: int) -> int:
    """Increment an integer synchronously."""

    return value + 1


def percentile(values: list[float], fraction: float) -> float:
    """Return a nearest-rank percentile for non-empty values."""

    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


async def benchmark(iterations: int, batch_size: int) -> dict[str, Any]:
    """Measure validated invocation latency and ordered batch throughput."""

    runtime = ToolRuntime(max_batch_size=batch_size)
    runtime.register(increment)
    runtime.register(increment_sync)
    try:
        for value in range(min(iterations, 100)):
            await runtime.invoke("increment", {"value": value})
            await runtime.invoke("increment_sync", {"value": value})

        async_sequential = await measure_sequential(runtime, "increment", iterations)
        sync_sequential = await measure_sequential(runtime, "increment_sync", iterations)
        async_batch = await measure_batch(runtime, "increment", batch_size)
        sync_batch = await measure_batch(runtime, "increment_sync", batch_size)
    finally:
        await runtime.aclose()

    return {
        "environment": {
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "samsarix_core": __version__,
        },
        "settings": {"batch_size": batch_size, "iterations": iterations},
        "async_sequential": async_sequential,
        "sync_sequential": sync_sequential,
        "async_single_batch": async_batch,
        "sync_single_batch": sync_batch,
    }


async def measure_sequential(
    runtime: ToolRuntime, tool_name: str, iterations: int
) -> dict[str, float]:
    """Measure one tool's sequential validated invocation path."""

    latencies: list[float] = []
    started = time.perf_counter()
    for value in range(iterations):
        call_started = time.perf_counter()
        result = await runtime.invoke(tool_name, {"value": value})
        if not result.success:
            raise RuntimeError(f"benchmark invocation failed: {result.to_dict()}")
        latencies.append((time.perf_counter() - call_started) * 1_000)
    elapsed = time.perf_counter() - started
    return {
        "calls_per_second": round(iterations / elapsed, 2),
        "latency_ms_mean": round(statistics.fmean(latencies), 4),
        "latency_ms_p50": round(percentile(latencies, 0.50), 4),
        "latency_ms_p95": round(percentile(latencies, 0.95), 4),
    }


async def measure_batch(runtime: ToolRuntime, tool_name: str, batch_size: int) -> dict[str, float]:
    """Measure one ordered batch for a tool."""

    calls = [ToolCall(tool_name, {"value": value}) for value in range(batch_size)]
    started = time.perf_counter()
    results = await runtime.invoke_many(calls)
    elapsed = time.perf_counter() - started
    if not all(result.success for result in results):
        raise RuntimeError("benchmark batch invocation failed")
    return {
        "calls_per_second": round(batch_size / elapsed, 2),
        "duration_ms": round(elapsed * 1_000, 4),
    }


def positive_integer(value: str) -> int:
    """Parse one positive command-line integer."""

    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be positive")
    return parsed


def main() -> None:
    """Run the benchmark and print machine-readable JSON."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iterations", type=positive_integer, default=2_000)
    parser.add_argument("--batch-size", type=positive_integer, default=256)
    arguments = parser.parse_args()
    report = asyncio.run(benchmark(arguments.iterations, arguments.batch_size))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
