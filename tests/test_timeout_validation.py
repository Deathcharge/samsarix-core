# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
import math

import pytest

from samsarix_core import (
    ToolCall,
    ToolCircuitBreaker,
    ToolCircuitState,
    ToolDefinitionError,
    ToolLifecycleStatus,
    ToolPolicyDecision,
    ToolRateLimit,
    ToolRegistry,
    ToolRuntime,
    ToolStatus,
    samsarix_tool,
)

INVALID_TIMEOUTS = [
    pytest.param(math.nan, id="nan"),
    pytest.param(math.inf, id="infinity"),
    pytest.param(-math.inf, id="negative-infinity"),
    pytest.param(10**1000, id="overflowing-integer"),
    pytest.param(-(10**1000), id="negative-overflowing-integer"),
]


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
def test_non_finite_timeout_metadata_is_rejected(timeout):
    def echo(value: int) -> int:
        """Return one value."""

        return value

    with pytest.raises(ToolDefinitionError, match="finite"):
        samsarix_tool(timeout=timeout)(echo)
    assert not hasattr(echo, "__samsarix_tool_config__")


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
def test_non_finite_runtime_defaults_are_rejected(timeout):
    with pytest.raises(ValueError, match="default_timeout.*finite"):
        ToolRuntime(default_timeout=timeout)


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
@pytest.mark.parametrize("synchronous", [False, True])
async def test_invalid_overrides_never_reach_policy_capacity_or_execution(timeout, synchronous):
    executed = []
    evaluated = []
    events = []

    @samsarix_tool
    def sync_echo(value: str) -> str:
        """Return one value from a worker."""

        executed.append(value)
        return value

    @samsarix_tool
    async def async_echo(value: str) -> str:
        """Return one value asynchronously."""

        executed.append(value)
        return value

    async def allow(context):
        evaluated.append(context.spec.name)
        return ToolPolicyDecision.ALLOW

    runtime = ToolRuntime(max_pending_invocations=1, policy=allow, lifecycle_handler=events.append)
    name = "sync_echo" if synchronous else "async_echo"
    runtime.register(
        sync_echo if synchronous else async_echo,
        rate_limit=ToolRateLimit(calls=1, period_seconds=60),
        circuit_breaker=ToolCircuitBreaker(failure_threshold=1, recovery_timeout_seconds=60),
    )
    try:
        invalid = await runtime.invoke(name, {"value": "private-timeout-input"}, timeout=timeout)
        assert invalid.status is ToolStatus.INVALID_ARGUMENTS
        assert invalid.error.code == "invalid_timeout"
        assert not invalid.error.retryable
        assert "private-timeout-input" not in json.dumps(invalid.to_dict(), allow_nan=False)
        assert executed == evaluated == []
        assert [event.status for event in events] == [
            ToolLifecycleStatus.STARTED,
            ToolLifecycleStatus.INVALID_ARGUMENTS,
        ]
        metrics = runtime.metrics()
        assert metrics.calls_total == metrics.invalid_arguments == 1
        assert metrics.peak_pending_invocations == metrics.peak_in_flight == 0
        assert metrics.failed == metrics.timed_out == metrics.circuit_breaker_trips == 0
        assert runtime.pending_sync_calls == 0
        assert runtime.circuit_state(name) is ToolCircuitState.CLOSED
        good = await runtime.invoke(name, {"value": "accepted"})
        assert good.success and good.output == "accepted"
        assert executed == ["accepted"] and evaluated == [name]
    finally:
        await runtime.aclose(wait_for_sync=True, timeout=1)


async def test_overflowing_timeout_does_not_abort_the_rest_of_a_batch():
    executed = []

    @samsarix_tool
    async def echo(value: int) -> int:
        """Return values only for valid invocations."""

        executed.append(value)
        return value

    async with ToolRuntime() as runtime:
        runtime.register(echo)
        results = await runtime.invoke_many(
            [
                ToolCall("echo", {"value": 1}, timeout=10**1000),
                ToolCall("echo", {"value": 2}),
                ToolCall("echo", {"value": 3}, timeout=math.nan),
                ToolCall("echo", {"value": 4}, timeout=1),
            ]
        )
    assert [result.status for result in results] == [
        ToolStatus.INVALID_ARGUMENTS,
        ToolStatus.SUCCESS,
        ToolStatus.INVALID_ARGUMENTS,
        ToolStatus.SUCCESS,
    ]
    assert results[1].output == 2 and results[3].output == 4
    assert sorted(executed) == [2, 4]
    assert runtime.metrics().pending_invocations == runtime.metrics().in_flight == 0


@pytest.mark.parametrize("timeout", INVALID_TIMEOUTS)
async def test_invalid_shutdown_timeout_does_not_close_or_cancel_active_work(timeout):
    started = asyncio.Event()
    release = asyncio.Event()

    @samsarix_tool
    async def waiting() -> str:
        """Remain active until explicitly released."""

        started.set()
        await release.wait()
        return "finished"

    runtime = ToolRuntime()
    runtime.register(waiting)
    task = asyncio.create_task(runtime.invoke("waiting", timeout=5))
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        with pytest.raises(ValueError, match="finite.*non-negative"):
            await runtime.wait_for_sync(timeout=timeout)
        with pytest.raises(ValueError, match="finite.*non-negative"):
            await runtime.aclose(wait_for_sync=True, timeout=timeout)
        assert not task.done()
        release.set()
        assert (await task).output == "finished"
        assert (await runtime.invoke("waiting")).success
    finally:
        release.set()
        await runtime.aclose()
        await asyncio.gather(task, return_exceptions=True)


async def test_timeout_precedence_and_zero_or_none_sync_waits_are_preserved(monkeypatch):
    observed = []
    wait_for = asyncio.wait_for

    async def observe(awaitable, timeout):
        observed.append(timeout)
        return await wait_for(awaitable, timeout)

    @samsarix_tool(timeout=2)
    async def decorated() -> str:
        """Use the decorated deadline by default."""

        return "ok"

    @samsarix_tool
    async def inherited() -> str:
        """Inherit the runtime's deadline."""

        return "ok"

    runtime = ToolRuntime(default_timeout=3)
    runtime.register(decorated)
    runtime.register(inherited)
    monkeypatch.setattr(asyncio, "wait_for", observe)
    try:
        assert (await runtime.invoke("decorated")).success
        assert (await runtime.invoke("decorated", timeout=1)).success
        assert (await runtime.invoke("inherited")).success
        assert observed == [2.0, 1.0, 3.0]
        assert await runtime.wait_for_sync(timeout=0)
        assert await runtime.wait_for_sync(timeout=None)
        assert await runtime.aclose(wait_for_sync=True, timeout=0)
        assert await runtime.aclose(wait_for_sync=True, timeout=None)
    finally:
        await runtime.aclose()


@pytest.mark.parametrize("timeout", [1, 0.25, 1e308])
async def test_finite_positive_timeouts_remain_valid_and_json_serializable(timeout):
    @samsarix_tool(timeout=timeout)
    async def echo() -> str:
        """Complete immediately under a finite deadline."""

        return "ok"

    spec = ToolRegistry().register(echo)
    assert spec.timeout == float(timeout)
    json.dumps(spec.to_dict(), allow_nan=False)
    async with ToolRuntime(default_timeout=timeout) as runtime:
        runtime.register(echo)
        assert (await runtime.invoke("echo", timeout=timeout)).output == "ok"
