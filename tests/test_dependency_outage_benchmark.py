# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
import runpy
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from samsarix_core import ToolRuntime, ToolStatus

SCRIPT = Path(__file__).resolve().parents[1] / "benchmarks" / "dependency_outage_benchmark.py"


@pytest.fixture
def benchmark():
    return SimpleNamespace(**runpy.run_path(str(SCRIPT)))


@pytest.mark.parametrize("scenario", ["GLOBAL_ONLY", "BULKHEAD", "BULKHEAD_CIRCUIT"])
async def test_outage_cohort_proves_results_isolation_and_actual_execution_counts(
    benchmark, scenario
):
    settings = benchmark.Settings(vendor_calls=8, local_calls=4, vendor_delay_ms=1, repeats=1)
    report = await benchmark.run_scenario(settings, benchmark.Scenario[scenario])
    guarded = scenario == "BULKHEAD_CIRCUIT"
    assert report["vendor_executions"] == (2 if guarded else 8)
    assert report["vendor_circuit_open"] == (6 if guarded else 0)
    assert report["vendor_peak_concurrency"] == (8 if scenario == "GLOBAL_ONLY" else 2)
    assert report["local_latency"]["count"] == 4
    assert report["vendor_latency"]["count"] == 8
    assert report["runtime_metrics"]["in_flight"] == 0
    assert report["runtime_metrics"]["pending_invocations"] == 0
    for key in ("vendor_latency", "local_latency"):
        assert 0 < report[key]["p50_ms"] <= report[key]["p95_ms"] <= report[key]["max_ms"]
    json.dumps(report, allow_nan=False)


async def test_outage_repetitions_preserve_every_run_and_rotate_order(benchmark):
    report = await benchmark.benchmark(
        benchmark.Settings(vendor_calls=8, local_calls=1, vendor_delay_ms=1, repeats=3)
    )
    assert report["report_version"] == 1
    assert len(report["runs"]) == 9
    names = [scenario.value for scenario in benchmark.Scenario]
    for index in range(3):
        runs = report["runs"][index * 3 : (index + 1) * 3]
        assert [run["scenario"] for run in runs] == names[index:] + names[:index]
        assert all(run["repetition"] == index + 1 for run in runs)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"vendor_calls": 7}, "vendor_calls"),
        ({"vendor_calls": 513}, "vendor_calls"),
        ({"local_calls": 0}, "local_calls"),
        ({"local_calls": 513}, "local_calls"),
        ({"vendor_delay_ms": 0}, "vendor_delay_ms"),
        ({"vendor_delay_ms": 101}, "vendor_delay_ms"),
        ({"repeats": 0}, "repeats"),
        ({"repeats": 11}, "repeats"),
        ({"vendor_calls": True}, "integer"),
        ({"local_calls": 2.5}, "integer"),
    ],
)
def test_outage_configuration_is_bounded(benchmark, kwargs, message):
    with pytest.raises(ValueError, match=message):
        benchmark.Settings(**kwargs)


@pytest.mark.parametrize("fault", ["output", "status", "private_error"])
async def test_outage_checker_rejects_corrupted_results(benchmark, monkeypatch, fault):
    invoke = ToolRuntime.invoke

    async def corrupt(self, name, *args, **kwargs):
        result = await invoke(self, name, *args, **kwargs)
        if fault == "output" and name == "cached_inventory":
            return replace(result, output=-1)
        if fault == "status" and name == "vendor_inventory":
            return replace(result, status=ToolStatus.TIMED_OUT)
        if fault == "private_error" and result.error is not None:
            return replace(
                result,
                error=replace(result.error, message="synthetic-private-vendor-detail"),
            )
        return result

    monkeypatch.setattr(ToolRuntime, "invoke", corrupt)
    message = {
        "output": "invalid result",
        "status": "failure count",
        "private_error": "detail leaked",
    }[fault]
    with pytest.raises(RuntimeError, match=message):
        await benchmark.run_scenario(
            benchmark.Settings(vendor_calls=8, vendor_delay_ms=1), benchmark.Scenario.GLOBAL_ONLY
        )


@pytest.mark.parametrize("control", ["circuit_breaker", "max_concurrency"])
async def test_outage_checker_detects_missing_control(benchmark, monkeypatch, control):
    register = ToolRuntime.register

    def omit_control(self, function, **kwargs):
        kwargs.pop(control, None)
        return register(self, function, **kwargs)

    monkeypatch.setattr(ToolRuntime, "register", omit_control)
    scenario = (
        benchmark.Scenario.BULKHEAD_CIRCUIT
        if control == "circuit_breaker"
        else benchmark.Scenario.BULKHEAD
    )
    with pytest.raises(RuntimeError, match="execution count|concurrency"):
        await benchmark.run_scenario(
            benchmark.Settings(vendor_calls=8, vendor_delay_ms=1), scenario
        )


async def test_outage_checker_detects_incorrect_runtime_counters(benchmark, monkeypatch):
    metrics = ToolRuntime.metrics
    monkeypatch.setattr(ToolRuntime, "metrics", lambda self: replace(metrics(self), failed=0))
    with pytest.raises(RuntimeError, match="counters disagree"):
        await benchmark.run_scenario(
            benchmark.Settings(vendor_calls=8, vendor_delay_ms=1), benchmark.Scenario.GLOBAL_ONLY
        )


@pytest.mark.parametrize("stop", ["deadline", "cancellation"])
async def test_outage_abort_reaps_tasks_and_closes_runtime(benchmark, monkeypatch, stop):
    invoke = ToolRuntime.invoke
    entered = asyncio.Event()
    children = []
    runtimes = set()

    async def hang(self, name, *args, **kwargs):
        if name == "vendor_inventory":
            runtimes.add(self)
            children.append(asyncio.current_task())
            entered.set()
            await asyncio.Event().wait()
        return await invoke(self, name, *args, **kwargs)

    monkeypatch.setattr(ToolRuntime, "invoke", hang)
    if stop == "deadline":
        monkeypatch.setattr(benchmark.Settings, "deadline_seconds", property(lambda self: 0.05))
    task = asyncio.create_task(
        benchmark.run_scenario(benchmark.Settings(vendor_calls=8), benchmark.Scenario.GLOBAL_ONLY)
    )
    await asyncio.wait_for(entered.wait(), timeout=5)
    if stop == "cancellation":
        task.cancel()
    with pytest.raises(asyncio.CancelledError if stop == "cancellation" else asyncio.TimeoutError):
        await asyncio.wait_for(task, timeout=5)
    assert len(children) == 8 and all(child.done() for child in children)
    for runtime in runtimes:
        assert runtime.metrics().in_flight == runtime.metrics().pending_invocations == 0
        assert (await runtime.invoke("cached_inventory")).status is ToolStatus.RUNTIME_CLOSED


def test_outage_cli_rejects_unbounded_settings_and_keeps_checks_under_optimization():
    invalid = subprocess.run(
        [sys.executable, str(SCRIPT), "--vendor-calls", "1000000"],
        capture_output=True,
        timeout=10,
    )
    assert invalid.returncode == 2
    assert b"between 8 and 512" in invalid.stderr
    assert invalid.stdout == b""
    optimized = subprocess.run(
        [
            sys.executable,
            "-I",
            "-O",
            "-c",
            f"import runpy; runpy.run_path({str(SCRIPT)!r})['require'](False, 'sentinel-failure')",
        ],
        capture_output=True,
        timeout=10,
    )
    assert optimized.returncode != 0
    assert b"sentinel-failure" in optimized.stderr
