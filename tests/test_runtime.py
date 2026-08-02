# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import math
import time
from threading import Event
from typing import Literal, TypedDict

import pytest

from samsarix_core import ToolCall, ToolRuntime, ToolStatus
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
        issue["code"] for issue in result.error.to_dict()["details"]["issues"]  # type: ignore[index,union-attr]
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
async def test_batch_size_is_bounded_before_workers_are_created() -> None:
    runtime = populated_runtime(max_batch_size=2)
    try:
        with pytest.raises(ValueError, match="maximum is 2"):
            await runtime.invoke_many([ToolCall("add", {"left": 1})] * 3)
    finally:
        await runtime.aclose()

    assert runtime.metrics().calls_total == 0


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
    assert metrics.in_flight == 0


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
        ({"default_timeout": 0}, ValueError),
        ({"default_timeout": True}, ValueError),
        ({"max_batch_size": 0}, ValueError),
        ({"max_batch_size": True}, TypeError),
        ({"max_argument_bytes": 0}, ValueError),
        ({"max_output_bytes": 1.5}, TypeError),
        ({"max_value_depth": 0}, ValueError),
        ({"max_value_nodes": True}, TypeError),
    ],
)
def test_runtime_configuration_is_validated(
    kwargs: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        ToolRuntime(**kwargs)  # type: ignore[arg-type]
