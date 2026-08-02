# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import math
import time
from collections.abc import Awaitable, Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from typing import Literal, TypedDict

import pytest

from samsarix_core import (
    ProgressHandlerError,
    ToolCall,
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolProgress,
    ToolResult,
    ToolRuntime,
    ToolStatus,
    report_progress,
)
from samsarix_core import samsarix_tool as helix_tool


class OptionalProfileFields(TypedDict, total=False):
    nickname: str


class ProfileInput(OptionalProfileFields):
    name: str
    scores: list[int]


class ProfileOutput(TypedDict):
    display_name: str
    total: int


@helix_tool
def add(left: int, right: int = 1) -> int:
    """Add two integers."""

    return left + right


@helix_tool
async def describe(
    values: list[int],
    mode: Literal["sum", "max"],
    label: str | None = None,
) -> dict[str, int | str | None]:
    """Describe integer values."""

    total = sum(values) if mode == "sum" else max(values)
    return {"label": label, "value": total}


@helix_tool(timeout=0.01)
async def slow(delay: float) -> str:
    """Wait briefly."""

    await asyncio.sleep(delay)
    return "done"


@helix_tool
def blocking(delay: float) -> str:
    """Block a worker thread briefly."""

    time.sleep(delay)
    return "done"


@helix_tool
def fail(secret: str) -> str:
    """Raise a test exception."""

    raise RuntimeError(f"sensitive:{secret}")


@helix_tool
def wrong_type() -> str:
    """Return a value that violates the declared contract."""

    return object()  # type: ignore[return-value]


@helix_tool
def non_finite() -> float:
    """Return a non-finite number."""

    return math.inf


def populated_runtime(**kwargs: object) -> ToolRuntime:
    runtime = ToolRuntime(**kwargs)  # type: ignore[arg-type]
    for tool in (add, describe, slow, blocking, fail, wrong_type, non_finite):
        runtime.register(tool)
    return runtime


def test_runtime_keeps_an_explicit_empty_registry() -> None:
    from samsarix_core import ToolRegistry

    registry = ToolRegistry()
    runtime = ToolRuntime(registry)
    try:
        assert runtime.registry is registry
    finally:
        asyncio.run(runtime.aclose())


@pytest.mark.asyncio
async def test_sync_and_async_tools_complete_with_normalized_defaults() -> None:
    runtime = populated_runtime()
    try:
        added = await runtime.invoke("add", {"left": 4})
        described = await runtime.invoke(
            "describe", {"values": [2, 5], "mode": "max", "label": None}
        )
    finally:
        await runtime.aclose()

    assert added.success is True
    assert added.status is ToolStatus.SUCCESS
    assert added.output == 5
    assert added.error is None
    assert described.output == {"label": None, "value": 5}
    assert described.to_dict()["status"] == "success"
    assert added.invocation_id != described.invocation_id
    assert added.started_at.endswith("+00:00")
    assert added.duration_ms >= 0


@pytest.mark.asyncio
async def test_argument_validation_reports_all_top_level_problems() -> None:
    runtime = populated_runtime()
    try:
        result = await runtime.invoke(
            "add",
            {"left": True, "extra": 4},
        )
        wrong_container = await runtime.invoke("add", [])  # type: ignore[arg-type]
        invalid_timeout = await runtime.invoke("add", {"left": 1}, timeout=0)
    finally:
        await runtime.aclose()

    assert result.status is ToolStatus.INVALID_ARGUMENTS
    assert result.error is not None
    issue_codes = {
        issue["code"]
        for issue in result.error.to_dict()["details"]["issues"]  # type: ignore[index,union-attr]
    }
    assert issue_codes == {"type_mismatch", "unexpected_argument"}
    assert wrong_container.error is not None
    assert wrong_container.error.code == "invalid_arguments"
    assert invalid_timeout.error is not None
    assert invalid_timeout.error.code == "invalid_timeout"


@pytest.mark.asyncio
async def test_nested_argument_validation_and_tuple_normalization() -> None:
    runtime = populated_runtime()
    try:
        invalid = await runtime.invoke("describe", {"values": [1, "two"], "mode": "median"})
        valid_float = await runtime.invoke("blocking", {"delay": 0})
    finally:
        await runtime.aclose()

    assert invalid.status is ToolStatus.INVALID_ARGUMENTS
    assert invalid.error is not None
    assert invalid.error.details is not None
    paths = {item["path"] for item in invalid.error.details["issues"]}  # type: ignore[index,union-attr]
    assert paths == {"$.values[1]", "$.mode"}
    assert valid_float.output == "done"


@pytest.mark.asyncio
async def test_typed_dict_invocation_validates_named_fields_and_nested_values() -> None:
    executions = 0

    @helix_tool
    def summarize_profile(profile: ProfileInput) -> ProfileOutput:
        """Summarize a typed profile."""

        nonlocal executions
        executions += 1
        return {"display_name": profile["name"].strip(), "total": sum(profile["scores"])}

    runtime = ToolRuntime()
    runtime.register(summarize_profile)
    try:
        valid = await runtime.invoke(
            "summarize_profile", {"profile": {"name": " Ada ", "scores": [2, 3]}}
        )
        invalid = await runtime.invoke(
            "summarize_profile",
            {"profile": {"scores": [1, "two"], "unknown": True}},
        )
    finally:
        await runtime.aclose()

    assert valid.output == {"display_name": "Ada", "total": 5}
    assert invalid.status is ToolStatus.INVALID_ARGUMENTS
    assert invalid.error is not None and invalid.error.details is not None
    issues = invalid.error.details["issues"]
    assert {(issue["path"], issue["code"]) for issue in issues} == {  # type: ignore[index,union-attr]
        ("$.profile.name", "missing_field"),
        ("$.profile.scores[1]", "type_mismatch"),
        ("$.profile.unknown", "unexpected_field"),
    }
    assert executions == 1


@pytest.mark.asyncio
async def test_typed_dict_output_contract_rejects_missing_and_extra_fields() -> None:
    @helix_tool
    def invalid_profile() -> ProfileOutput:
        """Return an invalid named result."""

        return {"display_name": "Ada", "extra": 1}  # type: ignore[return-value,typeddict-unknown-key]

    runtime = ToolRuntime()
    runtime.register(invalid_profile)
    try:
        result = await runtime.invoke("invalid_profile")
    finally:
        await runtime.aclose()

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.code == "invalid_output"
    assert result.error.message == "Tool output did not match its declared return type"


@pytest.mark.asyncio
async def test_unknown_tools_are_structured_results() -> None:
    runtime = ToolRuntime()
    try:
        result = await runtime.invoke("missing", {})
    finally:
        await runtime.aclose()

    assert result.status is ToolStatus.NOT_FOUND
    assert result.error is not None
    assert result.error.code == "tool_not_found"
    assert result.error.retryable is False


@pytest.mark.asyncio
async def test_timeout_covers_async_and_sync_execution() -> None:
    runtime = populated_runtime(default_timeout=0.01)
    try:
        async_result = await runtime.invoke("slow", {"delay": 0.1})
        sync_result = await runtime.invoke("blocking", {"delay": 0.05})
    finally:
        await runtime.aclose()

    assert async_result.status is ToolStatus.TIMED_OUT
    assert async_result.error is not None and async_result.error.retryable is False
    assert sync_result.status is ToolStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_timed_out_sync_work_remains_observable_and_holds_its_slot() -> None:
    started = Event()
    release = Event()

    @helix_tool
    def gated() -> str:
        """Wait for an external release signal."""

        started.set()
        release.wait(2)
        return "done"

    runtime = ToolRuntime(max_concurrency=1)
    runtime.register(gated)
    try:
        first = await runtime.invoke("gated", timeout=0.02)
        assert started.is_set()
        assert first.status is ToolStatus.TIMED_OUT
        assert runtime.pending_sync_calls == 1
        assert runtime.metrics().in_flight == 1

        second = await runtime.invoke("gated", timeout=0.02)
        assert second.status is ToolStatus.TIMED_OUT
        assert runtime.pending_sync_calls == 1
        assert await runtime.wait_for_sync(timeout=0) is False

        release.set()
        assert await runtime.wait_for_sync(timeout=1) is True
        assert runtime.pending_sync_calls == 0
        assert runtime.metrics().in_flight == 0
    finally:
        release.set()
        await runtime.aclose(wait_for_sync=True, timeout=1)


@pytest.mark.asyncio
async def test_timed_out_sync_work_holds_only_its_tool_bulkhead() -> None:
    started = Event()
    release = Event()
    executions = 0

    @helix_tool
    def isolated_blocker() -> str:
        """Block one downstream integration."""

        nonlocal executions
        executions += 1
        started.set()
        release.wait(2)
        return "released"

    @helix_tool
    async def healthy_tool() -> str:
        """Represent an unrelated healthy integration."""

        return "healthy"

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(isolated_blocker, max_concurrency=1)
    runtime.register(healthy_tool)
    try:
        first = await runtime.invoke("isolated_blocker", timeout=0.02)
        assert started.is_set()
        assert first.status is ToolStatus.TIMED_OUT

        queued = await runtime.invoke("isolated_blocker", timeout=0.02)
        healthy = await runtime.invoke("healthy_tool", timeout=0.2)

        assert queued.status is ToolStatus.TIMED_OUT
        assert executions == 1
        assert runtime.pending_sync_calls == 1
        assert healthy.output == "healthy"

        release.set()
        assert await runtime.wait_for_sync(timeout=1) is True
        recovered = await runtime.invoke("isolated_blocker", timeout=0.2)
        assert recovered.output == "released"
        assert executions == 2
    finally:
        release.set()
        await runtime.aclose(wait_for_sync=True, timeout=1)


@pytest.mark.asyncio
async def test_close_can_report_or_wait_for_sync_quiescence() -> None:
    release = Event()

    @helix_tool
    def gated() -> str:
        """Wait for an external release signal."""

        release.wait(2)
        return "done"

    runtime = ToolRuntime()
    runtime.register(gated)
    try:
        result = await runtime.invoke("gated", timeout=0.02)
        assert result.status is ToolStatus.TIMED_OUT
        assert await runtime.aclose() is False
        assert await runtime.aclose(wait_for_sync=True, timeout=0.01) is False

        rejected = await runtime.invoke("gated")
        assert rejected.status is ToolStatus.RUNTIME_CLOSED
        release.set()
        assert await runtime.aclose(wait_for_sync=True, timeout=1) is True
    finally:
        release.set()
        await runtime.aclose(wait_for_sync=True, timeout=1)


@pytest.mark.asyncio
async def test_close_cancels_an_active_wait_but_can_still_track_its_sync_thread() -> None:
    started = Event()
    release = Event()

    @helix_tool
    def gated() -> str:
        """Wait for an external release signal."""

        started.set()
        release.wait(2)
        return "done"

    runtime = ToolRuntime()
    runtime.register(gated)
    invocation = asyncio.create_task(runtime.invoke("gated", timeout=1))
    try:
        assert await asyncio.to_thread(started.wait, 1)
        assert await runtime.aclose(wait_for_sync=True, timeout=0.01) is False
        with pytest.raises(asyncio.CancelledError):
            await invocation
        assert runtime.pending_sync_calls == 1

        release.set()
        assert await runtime.wait_for_sync(timeout=1) is True
    finally:
        release.set()
        invocation.cancel()
        await asyncio.gather(invocation, return_exceptions=True)
        await runtime.aclose(wait_for_sync=True, timeout=1)


@pytest.mark.asyncio
async def test_sync_wait_and_close_options_are_validated_without_closing() -> None:
    runtime = ToolRuntime()
    try:
        with pytest.raises(ValueError, match="non-negative"):
            await runtime.wait_for_sync(timeout=-1)
        with pytest.raises(TypeError, match="boolean"):
            await runtime.aclose(wait_for_sync=1)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="requires"):
            await runtime.aclose(timeout=1)
        with pytest.raises(ValueError, match="non-negative"):
            await runtime.aclose(wait_for_sync=True, timeout=True)

        runtime.register(add)
        assert (await runtime.invoke("add", {"left": 1})).success
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_late_sync_failure_after_timeout_is_safely_consumed() -> None:
    release = Event()
    loop = asyncio.get_running_loop()
    loop_errors: list[dict[str, object]] = []
    previous_handler = loop.get_exception_handler()

    @helix_tool
    def late_failure() -> str:
        """Fail only after the caller has timed out."""

        release.wait(2)
        raise RuntimeError("late secret")

    runtime = ToolRuntime()
    runtime.register(late_failure)
    loop.set_exception_handler(lambda _, context: loop_errors.append(context))
    try:
        result = await runtime.invoke("late_failure", timeout=0.02)
        assert result.status is ToolStatus.TIMED_OUT
        release.set()
        assert await runtime.wait_for_sync(timeout=1) is True
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        release.set()
        await runtime.aclose(wait_for_sync=True, timeout=1)
        loop.set_exception_handler(previous_handler)

    assert loop_errors == []


@pytest.mark.asyncio
async def test_exceptions_are_redacted_by_default_and_can_be_opted_in() -> None:
    safe_runtime = populated_runtime()
    debug_runtime = populated_runtime(expose_exceptions=True)
    try:
        safe = await safe_runtime.invoke("fail", {"secret": "token"})
        debug = await debug_runtime.invoke("fail", {"secret": "token"})
    finally:
        await safe_runtime.aclose()
        await debug_runtime.aclose()

    assert safe.status is ToolStatus.FAILED
    assert safe.error is not None
    assert safe.error.message == "Tool execution failed"
    assert "token" not in str(safe.to_dict())
    assert debug.error is not None
    assert debug.error.message == "sensitive:token"
    assert debug.error.type == "RuntimeError"


@pytest.mark.asyncio
async def test_output_contract_and_json_compatibility_are_enforced() -> None:
    runtime = populated_runtime()
    try:
        wrong = await runtime.invoke("wrong_type", {})
        infinite = await runtime.invoke("non_finite", {})
    finally:
        await runtime.aclose()

    assert wrong.status is ToolStatus.FAILED
    assert wrong.error is not None and wrong.error.code == "invalid_output"
    assert infinite.status is ToolStatus.FAILED
    assert infinite.error is not None and infinite.error.code == "invalid_output"


@pytest.mark.asyncio
async def test_batch_preserves_order_and_bounds_execution() -> None:
    active = 0
    peak = 0

    @helix_tool
    async def tracked(value: int) -> int:
        """Track concurrent execution."""

        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return value

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(tracked)
    try:
        results = await runtime.invoke_many(
            [ToolCall("tracked", {"value": value}) for value in range(6)]
        )
        empty = await runtime.invoke_many([])
        metrics = runtime.metrics()
    finally:
        await runtime.aclose()

    assert [result.output for result in results] == list(range(6))
    assert peak == 2
    assert metrics.peak_in_flight == 2
    assert metrics.calls_total == 6
    assert metrics.succeeded == 6
    assert empty == []
    assert metrics.to_dict()["failed"] == 0


@pytest.mark.asyncio
async def test_per_tool_bulkhead_prevents_one_tool_from_starving_another() -> None:
    first_started = asyncio.Event()
    release = asyncio.Event()
    isolated_active = 0
    isolated_peak = 0

    @helix_tool
    async def isolated(value: int) -> int:
        """Hold calls to one constrained downstream integration."""

        nonlocal isolated_active, isolated_peak
        isolated_active += 1
        isolated_peak = max(isolated_peak, isolated_active)
        first_started.set()
        try:
            await release.wait()
            return value
        finally:
            isolated_active -= 1

    @helix_tool
    async def independent() -> str:
        """Complete through an unrelated integration."""

        return "available"

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(isolated, max_concurrency=1)
    runtime.register(independent)
    first = asyncio.create_task(runtime.invoke("isolated", {"value": 1}))
    second: asyncio.Task[ToolResult] | None = None
    try:
        await asyncio.wait_for(first_started.wait(), timeout=1)
        second = asyncio.create_task(runtime.invoke("isolated", {"value": 2}))
        for _ in range(100):
            if runtime.metrics().pending_invocations == 2:
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("second isolated invocation was not admitted")

        healthy = await asyncio.wait_for(runtime.invoke("independent"), timeout=0.2)
        assert healthy.output == "available"
        assert isolated_active == 1

        release.set()
        completed = await asyncio.gather(first, second)
        assert [result.output for result in completed] == [1, 2]
        assert isolated_peak == 1
    finally:
        release.set()
        first.cancel()
        if second is not None:
            second.cancel()
        await asyncio.gather(
            first, *(item for item in (second,) if item is not None), return_exceptions=True
        )
        await runtime.aclose()


@pytest.mark.asyncio
async def test_batch_calls_respect_the_registered_tool_bulkhead() -> None:
    active = 0
    peak = 0

    @helix_tool
    async def batch_isolated(value: int) -> int:
        """Track per-tool concurrency inside a batch."""

        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            return value
        finally:
            active -= 1

    runtime = ToolRuntime(max_concurrency=4)
    runtime.register(batch_isolated, max_concurrency=2)
    try:
        results = await runtime.invoke_many(
            [ToolCall("batch_isolated", {"value": value}) for value in range(8)]
        )
    finally:
        await runtime.aclose()

    assert [result.output for result in results] == list(range(8))
    assert peak == 2


@pytest.mark.asyncio
async def test_cancelling_a_tool_bulkhead_waiter_does_not_leak_capacity() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @helix_tool
    async def serial_tool(value: int) -> int:
        """Serialize calls behind an explicit tool bulkhead."""

        started.set()
        await release.wait()
        return value

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(serial_tool, max_concurrency=1)
    first = asyncio.create_task(runtime.invoke("serial_tool", {"value": 1}))
    waiter: asyncio.Task[ToolResult] | None = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        waiter = asyncio.create_task(runtime.invoke("serial_tool", {"value": 2}))
        await asyncio.sleep(0)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter

        release.set()
        assert (await first).output == 1
        recovered = await runtime.invoke("serial_tool", {"value": 3})
        assert recovered.output == 3
    finally:
        release.set()
        first.cancel()
        if waiter is not None:
            waiter.cancel()
        await asyncio.gather(
            first, *(item for item in (waiter,) if item is not None), return_exceptions=True
        )
        await runtime.aclose()


@pytest.mark.parametrize(
    ("limit", "error"),
    [
        (0, ValueError),
        (True, TypeError),
        (1.5, TypeError),
    ],
)
def test_per_tool_concurrency_is_validated_before_registration(
    limit: object, error: type[Exception]
) -> None:
    runtime = ToolRuntime()
    try:
        with pytest.raises(error):
            runtime.register(add, max_concurrency=limit)  # type: ignore[arg-type]
        assert "add" not in runtime.registry
    finally:
        asyncio.run(runtime.aclose())


@pytest.mark.asyncio
async def test_replacing_a_tool_does_not_inherit_its_previous_bulkhead() -> None:
    active = 0
    peak = 0

    @helix_tool(name="replaceable")
    async def original(value: int) -> int:
        """Represent the original constrained registration."""

        return value

    @helix_tool(name="replaceable")
    async def replacement(value: int) -> int:
        """Track concurrency for the replacement registration."""

        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            return value
        finally:
            active -= 1

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(original, max_concurrency=1)
    runtime.register(replacement, replace=True)
    try:
        results = await runtime.invoke_many(
            [
                ToolCall("replaceable", {"value": 1}),
                ToolCall("replaceable", {"value": 2}),
            ]
        )
    finally:
        await runtime.aclose()

    assert [result.output for result in results] == [1, 2]
    assert peak == 2


@pytest.mark.asyncio
async def test_concurrent_registrations_publish_every_tool_bulkhead() -> None:
    tool_count = 16
    active = [0] * tool_count
    peaks = [0] * tool_count

    def build_tool(index: int) -> Callable[[], Awaitable[int]]:
        @helix_tool(name=f"concurrent_{index}")
        async def concurrent_tool() -> int:
            """Track one concurrently registered tool's execution limit."""

            active[index] += 1
            peaks[index] = max(peaks[index], active[index])
            try:
                await asyncio.sleep(0.01)
                return index
            finally:
                active[index] -= 1

        return concurrent_tool

    runtime = ToolRuntime(max_concurrency=tool_count * 2)
    functions = [build_tool(index) for index in range(tool_count)]
    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            registrations = [
                executor.submit(runtime.register, function, max_concurrency=1)
                for function in functions
            ]
            assert {future.result().name for future in registrations} == {
                f"concurrent_{index}" for index in range(tool_count)
            }

        results = await runtime.invoke_many(
            [ToolCall(f"concurrent_{index}", {}) for index in range(tool_count) for _ in range(2)]
        )
    finally:
        await runtime.aclose()

    assert all(result.success for result in results)
    assert peaks == [1] * tool_count


@pytest.mark.asyncio
async def test_batch_size_is_bounded_before_workers_are_created() -> None:
    runtime = populated_runtime(max_batch_size=2)
    try:
        with pytest.raises(ValueError, match="maximum is 2"):
            await runtime.invoke_many([ToolCall("add", {"left": 1})] * 3)
    finally:
        await runtime.aclose()

    assert runtime.metrics().calls_total == 0


@pytest.mark.asyncio
async def test_runtime_sheds_excess_invocations_without_exposing_arguments() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @helix_tool
    async def admission_target(value: str) -> str:
        """Hold an admitted call until the test releases it."""

        started.set()
        await release.wait()
        return value

    runtime = ToolRuntime(max_concurrency=1, max_pending_invocations=2)
    runtime.register(admission_target)
    first = asyncio.create_task(runtime.invoke("admission_target", {"value": "first"}))
    second: asyncio.Task[ToolResult] | None = None
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        second = asyncio.create_task(runtime.invoke("admission_target", {"value": "second"}))
        for _ in range(100):
            if runtime.metrics().pending_invocations == 2:
                break
            await asyncio.sleep(0)
        else:
            pytest.fail("second invocation was not admitted")

        overloaded = await runtime.invoke("admission_target", {"value": "private-overload-value"})
        saturated = runtime.metrics()
        release.set()
        completed = await asyncio.gather(first, second)
        final = runtime.metrics()
    finally:
        release.set()
        first.cancel()
        if second is not None:
            second.cancel()
        await asyncio.gather(
            first, *(item for item in (second,) if item is not None), return_exceptions=True
        )
        await runtime.aclose()

    assert overloaded.status is ToolStatus.BUSY
    assert overloaded.error is not None
    assert overloaded.error.to_dict() == {
        "code": "runtime_busy",
        "message": "Runtime invocation capacity is full",
        "retryable": True,
    }
    assert "private-overload-value" not in str(overloaded.to_dict())
    assert [result.output for result in completed] == ["first", "second"]
    assert saturated.busy == 1
    assert saturated.pending_invocations == 2
    assert saturated.peak_pending_invocations == 2
    assert saturated.in_flight == 1
    assert final.calls_total == 3
    assert final.succeeded == 2
    assert final.busy == 1
    assert final.pending_invocations == 0


@pytest.mark.asyncio
async def test_batch_uses_pending_capacity_as_its_worker_bound() -> None:
    @helix_tool
    async def batch_admission_target(value: int) -> int:
        """Return one value after yielding to competing workers."""

        await asyncio.sleep(0)
        return value

    runtime = ToolRuntime(max_concurrency=4, max_pending_invocations=1)
    runtime.register(batch_admission_target)
    try:
        results = await runtime.invoke_many(
            [ToolCall("batch_admission_target", {"value": value}) for value in range(4)]
        )
        metrics = runtime.metrics()
    finally:
        await runtime.aclose()

    assert [result.output for result in results] == list(range(4))
    assert all(result.status is ToolStatus.SUCCESS for result in results)
    assert metrics.busy == 0
    assert metrics.peak_pending_invocations == 1


@pytest.mark.asyncio
async def test_policy_receives_detached_validated_calls_and_fails_closed_on_denial() -> None:
    executions: list[tuple[list[int], str]] = []
    snapshots: list[ToolPolicyContext] = []

    @helix_tool
    async def guarded_total(values: list[int], label: str = "default") -> int:
        """Sum values after the host policy allows execution."""

        executions.append((values, label))
        return sum(values)

    async def policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        snapshots.append(context)
        label = context.arguments["label"]
        context.arguments["values"].append(99)
        context.spec.input_schema.clear()
        return ToolPolicyDecision.DENY if label == "deny" else ToolPolicyDecision.ALLOW

    runtime = ToolRuntime(policy=policy)
    runtime.register(guarded_total)
    try:
        allowed = await runtime.invoke("guarded_total", {"values": [1, 2]})
        denied = await runtime.invoke("guarded_total", {"values": [4], "label": "deny"})
        invalid = await runtime.invoke("guarded_total", {"values": ["private"]})
        missing = await runtime.invoke("private-tool", {"secret": "value"})
        metrics = runtime.metrics()
    finally:
        await runtime.aclose()

    assert allowed.status is ToolStatus.SUCCESS
    assert allowed.output == 3
    assert denied.status is ToolStatus.DENIED
    assert denied.error is not None
    assert denied.error.to_dict() == {
        "code": "tool_denied",
        "message": "Tool invocation was denied by host policy",
        "retryable": False,
    }
    assert invalid.status is ToolStatus.INVALID_ARGUMENTS
    assert missing.status is ToolStatus.NOT_FOUND
    assert executions == [([1, 2], "default")]
    assert len(snapshots) == 2
    assert snapshots[0].invocation_id == allowed.invocation_id
    assert snapshots[1].invocation_id == denied.invocation_id
    assert snapshots[0].arguments["label"] == "default"
    assert runtime.registry.get("guarded_total").input_schema["properties"]
    assert metrics.calls_total == 4
    assert metrics.succeeded == 1
    assert metrics.denied == 1
    assert metrics.invalid_arguments == 1
    assert metrics.not_found == 1
    assert metrics.in_flight == 0
    assert metrics.to_dict()["denied"] == 1


@pytest.mark.asyncio
async def test_policy_exceptions_and_invalid_decisions_are_safe_failures() -> None:
    executions = 0

    @helix_tool
    async def policy_target(mode: Literal["raise", "invalid"]) -> str:
        """Run only after a valid policy decision."""

        nonlocal executions
        executions += 1
        return mode

    async def broken_policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        if context.arguments["mode"] == "raise":
            raise RuntimeError("private-policy-detail")
        return "allow"  # type: ignore[return-value]

    runtime = ToolRuntime(policy=broken_policy, expose_exceptions=True)
    runtime.register(policy_target)
    try:
        raised = await runtime.invoke("policy_target", {"mode": "raise"})
        invalid = await runtime.invoke("policy_target", {"mode": "invalid"})
        metrics = runtime.metrics()
    finally:
        await runtime.aclose()

    for result in (raised, invalid):
        assert result.status is ToolStatus.FAILED
        assert result.error is not None
        assert result.error.to_dict() == {
            "code": "tool_policy_failed",
            "message": "Tool invocation policy failed",
            "retryable": False,
        }
        assert "private-policy-detail" not in str(result.to_dict())
    assert executions == 0
    assert metrics.failed == 2
    assert metrics.denied == 0
    assert metrics.in_flight == 0


@pytest.mark.asyncio
async def test_policy_timeout_and_cancellation_stop_before_tool_execution() -> None:
    started = {name: asyncio.Event() for name in ("timeout", "cancel", "allow")}
    stopped = {name: asyncio.Event() for name in ("timeout", "cancel")}
    release = {name: asyncio.Event() for name in ("timeout", "cancel", "allow")}
    executions: list[str] = []

    @helix_tool
    async def policy_wait_target(value: str) -> str:
        """Return a value only after policy completion."""

        executions.append(value)
        return value

    async def waiting_policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        value = context.arguments["value"]
        started[value].set()
        try:
            await release[value].wait()
        finally:
            if value in stopped:
                stopped[value].set()
        return ToolPolicyDecision.ALLOW

    runtime = ToolRuntime(policy=waiting_policy, max_concurrency=1)
    runtime.register(policy_wait_target)
    try:
        timed_out = await runtime.invoke("policy_wait_target", {"value": "timeout"}, timeout=0.01)
        await asyncio.wait_for(stopped["timeout"].wait(), timeout=1)

        cancelled_call = asyncio.create_task(
            runtime.invoke("policy_wait_target", {"value": "cancel"}, timeout=1)
        )
        await asyncio.wait_for(started["cancel"].wait(), timeout=1)
        cancelled_call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await cancelled_call
        await asyncio.wait_for(stopped["cancel"].wait(), timeout=1)

        release["allow"].set()
        allowed = await runtime.invoke("policy_wait_target", {"value": "allow"}, timeout=1)
        metrics = runtime.metrics()
    finally:
        for event in release.values():
            event.set()
        await runtime.aclose()

    assert timed_out.status is ToolStatus.TIMED_OUT
    assert allowed.output == "allow"
    assert executions == ["allow"]
    assert metrics.timed_out == 1
    assert metrics.cancelled == 1
    assert metrics.succeeded == 1
    assert metrics.in_flight == 0


@pytest.mark.asyncio
async def test_policy_evaluation_concurrency_is_bounded() -> None:
    active = 0
    peak = 0

    @helix_tool
    async def policy_concurrency_target(value: int) -> int:
        """Return one policy-approved value."""

        return value

    async def bounded_policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        del context
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return ToolPolicyDecision.ALLOW

    runtime = ToolRuntime(policy=bounded_policy, max_concurrency=2)
    runtime.register(policy_concurrency_target)
    try:
        results = await asyncio.gather(
            *(runtime.invoke("policy_concurrency_target", {"value": value}) for value in range(6))
        )
    finally:
        await runtime.aclose()

    assert [result.output for result in results] == list(range(6))
    assert peak == 2


def test_policy_must_be_an_async_callable() -> None:
    with pytest.raises(TypeError, match="async callable"):
        ToolRuntime(policy=lambda context: ToolPolicyDecision.ALLOW)  # type: ignore[arg-type]

    class AsyncPolicy:
        async def __call__(self, context: ToolPolicyContext) -> ToolPolicyDecision:
            del context
            return ToolPolicyDecision.ALLOW

    runtime = ToolRuntime(policy=AsyncPolicy())
    asyncio.run(runtime.aclose())


@pytest.mark.asyncio
async def test_argument_resource_limits_reject_size_depth_nodes_and_cycles() -> None:
    executed = False

    @helix_tool
    def nested(values: list[list[int]]) -> int:
        """Count nested values."""

        nonlocal executed
        executed = True
        return sum(len(value) for value in values)

    cases: list[tuple[ToolRuntime, dict[str, object], str]] = [
        (ToolRuntime(max_argument_bytes=16), {"values": [[123456789]]}, "value_too_large"),
        (ToolRuntime(max_value_depth=2), {"values": [[1]]}, "value_too_deep"),
        (ToolRuntime(max_value_nodes=3), {"values": [[1]]}, "value_too_complex"),
    ]
    cyclic: list[object] = []
    cyclic.append(cyclic)
    cases.append((ToolRuntime(), {"values": cyclic}, "cyclic_value"))

    try:
        for runtime, arguments, expected_code in cases:
            runtime.register(nested)
            result = await runtime.invoke("nested", arguments)
            assert result.status is ToolStatus.INVALID_ARGUMENTS
            assert result.error is not None
            issues = result.error.details["issues"]  # type: ignore[index]
            assert issues[0]["code"] == expected_code  # type: ignore[index]
    finally:
        await asyncio.gather(*(runtime.aclose() for runtime, _, _ in cases))

    assert executed is False


@pytest.mark.asyncio
async def test_resource_walker_is_lazy_and_allows_shared_noncyclic_values() -> None:
    class CountingList(list[int]):
        yielded = 0

        def __iter__(self):  # type: ignore[no-untyped-def]
            for item in super().__iter__():
                self.yielded += 1
                yield item

    @helix_tool
    def total(values: list[list[int]]) -> int:
        """Sum nested values."""

        return sum(sum(value) for value in values)

    huge = CountingList(range(100_000))
    limited_runtime = ToolRuntime(max_value_nodes=3)
    shared_runtime = ToolRuntime()
    limited_runtime.register(total)
    shared_runtime.register(total)
    shared = [1]
    try:
        limited = await limited_runtime.invoke("total", {"values": [huge]})
        accepted = await shared_runtime.invoke("total", {"values": [shared, shared]})
    finally:
        await limited_runtime.aclose()
        await shared_runtime.aclose()

    assert limited.status is ToolStatus.INVALID_ARGUMENTS
    assert huge.yielded <= 2
    assert accepted.output == 2


@pytest.mark.asyncio
async def test_output_resource_limits_are_safe_structured_failures() -> None:
    @helix_tool
    def oversized() -> str:
        """Return a large string."""

        return "secret-value"

    @helix_tool
    def too_deep() -> list[list[int]]:
        """Return nested values."""

        return [[1]]

    size_runtime = ToolRuntime(max_output_bytes=8)
    depth_runtime = ToolRuntime(max_value_depth=1)
    size_runtime.register(oversized)
    depth_runtime.register(too_deep)
    try:
        size_result = await size_runtime.invoke("oversized")
        depth_result = await depth_runtime.invoke("too_deep")
    finally:
        await size_runtime.aclose()
        await depth_runtime.aclose()

    for result in (size_result, depth_result):
        assert result.status is ToolStatus.FAILED
        assert result.error is not None
        assert result.error.code == "output_limit_exceeded"
        assert result.error.message == "Tool output exceeded a configured resource limit"
        assert "secret-value" not in str(result.to_dict())


@pytest.mark.asyncio
async def test_cancellation_propagates_and_updates_content_free_metrics() -> None:
    runtime = populated_runtime()
    invocation = asyncio.create_task(runtime.invoke("slow", {"delay": 1}, timeout=2))
    await asyncio.sleep(0)
    invocation.cancel()

    with pytest.raises(asyncio.CancelledError):
        await invocation

    metrics = runtime.metrics()
    await runtime.aclose()
    assert metrics.cancelled == 1
    assert metrics.pending_invocations == 0
    assert metrics.in_flight == 0


@pytest.mark.asyncio
async def test_cancellation_closes_progress_before_tool_cleanup() -> None:
    started = asyncio.Event()
    never_release = asyncio.Event()
    cleanup_delivery: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    @helix_tool
    async def cancellable_progress() -> str:
        """Try to report from cleanup after cancellation."""

        assert await report_progress(1)
        started.set()
        try:
            await never_release.wait()
        finally:
            cleanup_delivery.set_result(await report_progress(2))
        return "unexpected"

    updates: list[ToolProgress] = []
    runtime = ToolRuntime()
    runtime.register(cancellable_progress)
    invocation = asyncio.create_task(
        runtime.invoke("cancellable_progress", progress_handler=updates.append)
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=1)
        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation
        assert cleanup_delivery.result() is False
    finally:
        await runtime.aclose()

    assert updates == [ToolProgress(progress=1.0)]


@pytest.mark.asyncio
async def test_timeout_closes_progress_before_tool_cleanup() -> None:
    never_release = asyncio.Event()
    cleanup_delivery: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    @helix_tool(timeout=0.01)
    async def timed_progress() -> str:
        """Try to report from cleanup after timeout."""

        assert await report_progress(1)
        try:
            await never_release.wait()
        finally:
            cleanup_delivery.set_result(await report_progress(2))
        return "unexpected"

    updates: list[ToolProgress] = []
    runtime = ToolRuntime()
    runtime.register(timed_progress)
    try:
        result = await runtime.invoke("timed_progress", progress_handler=updates.append)
    finally:
        await runtime.aclose()

    assert result.status is ToolStatus.TIMED_OUT
    assert cleanup_delivery.result() is False
    assert updates == [ToolProgress(progress=1.0)]


@pytest.mark.asyncio
async def test_runtime_close_stops_progress_before_cancelling_active_tools() -> None:
    started = asyncio.Event()
    never_release = asyncio.Event()
    cleanup_delivery: asyncio.Future[bool] = asyncio.get_running_loop().create_future()

    @helix_tool
    async def closing_progress() -> str:
        """Try to report from cleanup during runtime close."""

        assert await report_progress(1)
        started.set()
        try:
            await never_release.wait()
        finally:
            cleanup_delivery.set_result(await report_progress(2))
        return "unexpected"

    updates: list[ToolProgress] = []
    runtime = ToolRuntime()
    runtime.register(closing_progress)
    invocation = asyncio.create_task(
        runtime.invoke("closing_progress", progress_handler=updates.append)
    )
    await asyncio.wait_for(started.wait(), timeout=1)

    assert await runtime.aclose()
    with pytest.raises(asyncio.CancelledError):
        await invocation

    assert cleanup_delivery.result() is False
    assert updates == [ToolProgress(progress=1.0)]


@pytest.mark.asyncio
async def test_async_tools_report_bounded_monotonic_progress() -> None:
    delivery_results: list[bool] = []

    @helix_tool
    async def progressive() -> list[bool]:
        """Report more updates than the runtime permits."""

        delivery_results.append(await report_progress(1, total=3, message="started"))
        delivery_results.append(await report_progress(2, total=3))
        delivery_results.append(await report_progress(3, total=3, message="capped"))
        return delivery_results

    updates: list[ToolProgress] = []
    handler_reports: list[bool] = []

    async def collect(update: ToolProgress) -> None:
        updates.append(update)
        handler_reports.append(await report_progress(999))

    runtime = ToolRuntime(max_progress_updates=2)
    runtime.register(progressive)
    try:
        result = await runtime.invoke("progressive", progress_handler=collect)
    finally:
        await runtime.aclose()

    assert result.output == [True, True, False]
    assert updates == [
        ToolProgress(progress=1.0, total=3.0, message="started"),
        ToolProgress(progress=2.0, total=3.0),
    ]
    assert handler_reports == [False, False]
    assert await report_progress(4) is False


@pytest.mark.asyncio
async def test_progress_scope_closes_before_detached_tool_work_can_report() -> None:
    release = asyncio.Event()
    child_result: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
    pending: list[asyncio.Task[None]] = []

    @helix_tool
    async def spawn_reporter() -> str:
        """Start a child that attempts a late progress update."""

        async def report_later() -> None:
            await release.wait()
            child_result.set_result(await report_progress(2))

        pending.append(asyncio.create_task(report_later()))
        assert await report_progress(1)
        return "done"

    updates: list[ToolProgress] = []
    runtime = ToolRuntime()
    runtime.register(spawn_reporter)
    try:
        assert (await runtime.invoke("spawn_reporter", progress_handler=updates.append)).success
        release.set()
        assert await asyncio.wait_for(child_result, timeout=1) is False
        await pending[0]
    finally:
        release.set()
        await runtime.aclose()

    assert updates == [ToolProgress(progress=1.0)]


@pytest.mark.asyncio
async def test_progress_validation_fails_safely_inside_a_tool() -> None:
    @helix_tool
    async def invalid_progress() -> str:
        """Repeat a progress value in violation of the contract."""

        await report_progress(1, message="x")
        await report_progress(1)
        return "unexpected"

    @helix_tool
    async def oversized_progress_message() -> str:
        """Exceed the configured UTF-8 progress-message limit."""

        await report_progress(1, message="é")
        return "unexpected"

    @helix_tool
    async def invalid_progress_message() -> str:
        """Supply a non-string progress message."""

        await report_progress(1, message=1)  # type: ignore[arg-type]
        return "unexpected"

    runtime = ToolRuntime(max_progress_message_bytes=1)
    runtime.register(invalid_progress)
    runtime.register(oversized_progress_message)
    runtime.register(invalid_progress_message)
    try:
        result = await runtime.invoke("invalid_progress", progress_handler=lambda update: None)
        oversized = await runtime.invoke(
            "oversized_progress_message", progress_handler=lambda update: None
        )
        invalid_message = await runtime.invoke(
            "invalid_progress_message", progress_handler=lambda update: None
        )
        with pytest.raises(TypeError, match="progress_handler"):
            await runtime.invoke("invalid_progress", progress_handler=True)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="progress"):
            await report_progress(True)
        with pytest.raises(ValueError, match="finite"):
            await report_progress(float("inf"))
        with pytest.raises(ValueError, match="finite"):
            await report_progress(10**1_000)
    finally:
        await runtime.aclose()

    assert result.status is ToolStatus.FAILED
    assert result.error is not None
    assert result.error.message == "Tool execution failed"
    assert oversized.status is ToolStatus.FAILED
    assert invalid_message.status is ToolStatus.FAILED


@pytest.mark.asyncio
async def test_progress_handler_failures_propagate_as_host_errors() -> None:
    @helix_tool
    async def reporting_tool() -> str:
        """Emit one update through a failing host callback."""

        await report_progress(1)
        return "unexpected"

    def broken_handler(update: ToolProgress) -> None:
        raise OSError("progress transport failed")

    runtime = ToolRuntime()
    runtime.register(reporting_tool)
    try:
        with pytest.raises(ProgressHandlerError, match="Progress handler failed") as raised:
            await runtime.invoke("reporting_tool", progress_handler=broken_handler)
    finally:
        await runtime.aclose()

    assert runtime.metrics().failed == 0
    assert isinstance(raised.value.__cause__, OSError)


@pytest.mark.asyncio
async def test_close_is_idempotent_and_rejects_new_calls() -> None:
    runtime = populated_runtime()
    await runtime.aclose()
    await runtime.aclose()

    result = await runtime.invoke("add", {"left": 1})
    assert result.status is ToolStatus.RUNTIME_CLOSED
    assert result.error is not None and result.error.code == "runtime_closed"
    assert runtime.metrics().runtime_closed == 1


@pytest.mark.asyncio
async def test_async_context_manager_closes_the_runtime() -> None:
    async with ToolRuntime() as runtime:
        runtime.register(add)
        assert (await runtime.invoke("add", {"left": 2})).output == 3

    assert (await runtime.invoke("add", {"left": 2})).status is ToolStatus.RUNTIME_CLOSED


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"max_concurrency": 0}, ValueError),
        ({"max_concurrency": True}, TypeError),
        ({"max_pending_invocations": 0}, ValueError),
        ({"max_pending_invocations": True}, TypeError),
        ({"default_timeout": 0}, ValueError),
        ({"default_timeout": True}, ValueError),
        ({"max_batch_size": 0}, ValueError),
        ({"max_batch_size": True}, TypeError),
        ({"max_argument_bytes": 0}, ValueError),
        ({"max_output_bytes": 1.5}, TypeError),
        ({"max_value_depth": 0}, ValueError),
        ({"max_value_nodes": True}, TypeError),
        ({"max_progress_updates": 0}, ValueError),
        ({"max_progress_message_bytes": True}, TypeError),
    ],
)
def test_runtime_configuration_is_validated(
    kwargs: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        ToolRuntime(**kwargs)  # type: ignore[arg-type]
