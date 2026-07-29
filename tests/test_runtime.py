# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import math
import time
from typing import Literal

import pytest

from samsarix_core import ToolCall, ToolRuntime, ToolStatus
from samsarix_core import samsarix_tool as helix_tool


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
    ],
)
def test_runtime_configuration_is_validated(
    kwargs: dict[str, object], error: type[Exception]
) -> None:
    with pytest.raises(error):
        ToolRuntime(**kwargs)  # type: ignore[arg-type]
