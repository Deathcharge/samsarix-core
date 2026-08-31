# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Compare mixed-tool availability during a bounded synthetic dependency outage."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import platform
import statistics
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from samsarix_core import (
    ToolCircuitBreaker,
    ToolCircuitState,
    ToolResult,
    ToolRuntime,
    ToolStatus,
    __version__,
    samsarix_tool,
)

GLOBAL_CAPACITY = 8
VENDOR_CAPACITY = 2


class Scenario(str, Enum):
    GLOBAL_ONLY = "global_only"
    BULKHEAD = "bulkhead"
    BULKHEAD_CIRCUIT = "bulkhead_circuit"


@dataclass(frozen=True)
class Settings:
    vendor_calls: int = 64
    local_calls: int = 32
    vendor_delay_ms: int = 20
    repeats: int = 3

    def __post_init__(self) -> None:
        for name, minimum, maximum in (
            ("vendor_calls", GLOBAL_CAPACITY, 512),
            ("local_calls", 1, 512),
            ("vendor_delay_ms", 1, 100),
            ("repeats", 1, 10),
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{name} must be an integer")
            if not minimum <= value <= maximum:
                raise ValueError(f"{name} must be between {minimum} and {maximum}")

    @property
    def deadline_seconds(self) -> float:
        # Generous bound even if all synthetic vendor work executes sequentially.
        return 5 + self.vendor_calls * self.vendor_delay_ms / 1_000


def require(condition: bool, message: str) -> None:
    """Fail closed even when Python runs with optimization enabled."""

    if not condition:
        raise RuntimeError(message)


def latency_summary(values: list[float]) -> dict[str, float | int]:
    """Summarize all observed latencies, using nearest-rank percentiles."""

    ordered = sorted(values)
    return {
        "count": len(values),
        "mean_ms": round(statistics.fmean(values), 4),
        "p50_ms": round(ordered[math.ceil(len(values) * 0.5) - 1], 4),
        "p95_ms": round(ordered[math.ceil(len(values) * 0.95) - 1], 4),
        "max_ms": round(ordered[-1], 4),
    }


async def run_scenario(settings: Settings, scenario: Scenario) -> dict[str, Any]:
    """Run one fresh-runtime cohort with an overall cooperative deadline."""

    if not isinstance(scenario, Scenario):
        raise ValueError("scenario must be a Scenario")
    return await asyncio.wait_for(_measure(settings, scenario), settings.deadline_seconds)


async def _measure(settings: Settings, scenario: Scenario) -> dict[str, Any]:
    isolated = scenario is not Scenario.GLOBAL_ONLY
    guarded = scenario is Scenario.BULKHEAD_CIRCUIT
    capacity = VENDOR_CAPACITY if isolated else GLOBAL_CAPACITY
    saturated = asyncio.Event()
    release_vendor = asyncio.Event()
    vendor_executions = 0
    vendor_active = 0
    vendor_peak = 0

    @samsarix_tool(read_only=True)
    async def vendor_inventory(sku: int) -> int:
        """Model a read-only vendor outage without using the network."""

        nonlocal vendor_executions, vendor_active, vendor_peak
        vendor_executions += 1
        vendor_active += 1
        vendor_peak = max(vendor_peak, vendor_active)
        if vendor_active == capacity:
            saturated.set()
        try:
            await release_vendor.wait()
            await asyncio.sleep(settings.vendor_delay_ms / 1_000)
            raise ConnectionError("synthetic-private-vendor-detail")
        finally:
            vendor_active -= 1

    @samsarix_tool(read_only=True)
    async def cached_inventory(sku: int) -> int:
        """Return a deterministic local-cache value unrelated to vendor health."""

        return sku + 100

    runtime = ToolRuntime(
        max_concurrency=GLOBAL_CAPACITY,
        max_pending_invocations=settings.vendor_calls + settings.local_calls,
        default_timeout=settings.deadline_seconds,
    )
    runtime.register(
        vendor_inventory,
        max_concurrency=VENDOR_CAPACITY if isolated else None,
        circuit_breaker=(
            ToolCircuitBreaker(
                failure_threshold=1,
                recovery_timeout_seconds=settings.deadline_seconds * 2,
            )
            if guarded
            else None
        ),
    )
    runtime.register(cached_inventory)
    tasks: list[asyncio.Task[tuple[ToolResult, float]]] = []

    async def invoke(name: str, sku: int, submitted: float) -> tuple[ToolResult, float]:
        result = await runtime.invoke(name, {"sku": sku})
        return result, (time.perf_counter() - submitted) * 1_000

    started = time.perf_counter()
    try:
        tasks.extend(
            asyncio.create_task(invoke("vendor_inventory", sku, time.perf_counter()))
            for sku in range(settings.vendor_calls)
        )
        # All scenarios begin with the vendor's execution capacity occupied.
        # The barrier, not a guessed startup sleep, establishes that condition.
        await saturated.wait()
        tasks.extend(
            asyncio.create_task(invoke("cached_inventory", sku, time.perf_counter()))
            for sku in range(settings.local_calls)
        )
        release_vendor.set()
        measured = await asyncio.gather(*tasks)
        elapsed_ms = (time.perf_counter() - started) * 1_000
        vendor = measured[: settings.vendor_calls]
        local = measured[settings.vendor_calls :]
        expected_executions = VENDOR_CAPACITY if guarded else settings.vendor_calls
        expected_rejections = settings.vendor_calls - expected_executions
        require(vendor_executions == expected_executions, "unexpected vendor execution count")
        require(vendor_peak == capacity, "vendor concurrency did not match the scenario")
        require(vendor_active == 0, "vendor work did not finish")
        require(
            sum(result.status is ToolStatus.FAILED for result, _ in vendor) == expected_executions,
            "unexpected vendor failure count",
        )
        require(
            sum(result.status is ToolStatus.CIRCUIT_OPEN for result, _ in vendor)
            == expected_rejections,
            "unexpected circuit rejection count",
        )
        for result, _ in vendor:
            require(result.output is None and result.error is not None, "unsafe vendor result")
            require(
                "synthetic-private-vendor-detail" not in json.dumps(result.to_dict()),
                "vendor exception detail leaked",
            )
        for sku, (result, _) in enumerate(local):
            require(
                result.success and type(result.output) is int and result.output == sku + 100,
                "local cache returned an invalid result",
            )
        metrics = runtime.metrics()
        require(
            metrics.calls_total == settings.vendor_calls + settings.local_calls
            and metrics.failed == expected_executions
            and metrics.succeeded == settings.local_calls
            and metrics.circuit_open == expected_rejections
            and metrics.circuit_breaker_trips == int(guarded),
            "runtime counters disagree with observed outcomes",
        )
        require(
            metrics.in_flight == metrics.pending_invocations == 0
            and metrics.peak_in_flight <= GLOBAL_CAPACITY,
            "runtime capacity did not remain bounded or drain",
        )
        require(
            runtime.circuit_state("vendor_inventory")
            is (ToolCircuitState.OPEN if guarded else None),
            "unexpected terminal circuit state",
        )
        return {
            "scenario": scenario.value,
            "cohort_duration_ms": round(elapsed_ms, 4),
            "vendor_executions": vendor_executions,
            "vendor_peak_concurrency": vendor_peak,
            "vendor_failed": expected_executions,
            "vendor_circuit_open": expected_rejections,
            "vendor_latency": latency_summary([latency for _, latency in vendor]),
            "local_latency": latency_summary([latency for _, latency in local]),
            "runtime_metrics": metrics.to_dict(),
        }
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
        finally:
            require(
                await runtime.aclose(wait_for_sync=True, timeout=5),
                "runtime did not become quiescent",
            )


async def benchmark(settings: Settings) -> dict[str, Any]:
    """Retain every repetition, rotating scenario order to reduce order bias."""

    runs = []
    scenarios = list(Scenario)
    for repetition in range(settings.repeats):
        offset = repetition % len(scenarios)
        for scenario in scenarios[offset:] + scenarios[:offset]:
            result = await run_scenario(settings, scenario)
            runs.append({"repetition": repetition + 1, **result})
    source = await asyncio.to_thread(Path(__file__).read_bytes)
    return {
        "report_version": 1,
        "workload": "synthetic_async_dependency_outage",
        "environment": {
            "implementation": platform.python_implementation(),
            "platform": platform.platform(),
            "python": platform.python_version(),
            "samsarix_core": __version__,
            "benchmark_sha256": hashlib.sha256(source).hexdigest(),
        },
        "settings": {
            **asdict(settings),
            "global_max_concurrency": GLOBAL_CAPACITY,
            "vendor_bulkhead_concurrency": VENDOR_CAPACITY,
            "circuit_failure_threshold": 1,
            "circuit_recovery_seconds": settings.deadline_seconds * 2,
            "scenario_deadline_seconds": settings.deadline_seconds,
        },
        "runs": runs,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vendor-calls", type=int, default=64)
    parser.add_argument("--local-calls", type=int, default=32)
    parser.add_argument("--vendor-delay-ms", type=int, default=20)
    parser.add_argument("--repeats", type=int, default=3)
    arguments = parser.parse_args()
    try:
        settings = Settings(**vars(arguments))
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(asyncio.run(benchmark(settings)), indent=2, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
