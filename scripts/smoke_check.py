# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify installed public exports and real runtime behavior without dependencies."""

from __future__ import annotations

import asyncio
from importlib.metadata import version
from typing import TypedDict

import helix_core
import samsarix_core


class _SmokeRow(TypedDict):
    value: int


def _require(condition: bool, message: str) -> None:
    """Fail the smoke check even when Python assertions are optimized away."""

    if not condition:
        raise RuntimeError(message)


def main() -> None:
    """Assert the release-critical import and model surface."""

    canonical_exports = (
        samsarix_core.MCPServer,
        samsarix_core.ToolPolicyContext,
        samsarix_core.ToolPolicyDecision,
        samsarix_core.ToolRuntime,
        samsarix_core.serve_stdio,
    )
    legacy_exports = (
        helix_core.MCPServer,
        helix_core.ToolPolicyContext,
        helix_core.ToolPolicyDecision,
        helix_core.ToolRuntime,
        helix_core.serve_stdio,
    )
    _require(legacy_exports == canonical_exports, "legacy callable exports differ")
    _require(
        helix_core.ToolRateLimit is samsarix_core.ToolRateLimit,
        "legacy rate-limit export differs",
    )
    _require(
        helix_core.ToolCircuitBreaker is samsarix_core.ToolCircuitBreaker,
        "legacy circuit-policy export differs",
    )
    _require(
        helix_core.ToolCircuitState is samsarix_core.ToolCircuitState,
        "legacy circuit-state export differs",
    )
    _require(
        helix_core.__version__ == samsarix_core.__version__,
        "legacy package version differs",
    )
    _require(
        version("samsarix-core") == samsarix_core.__version__,
        "distribution and import versions differ",
    )
    _require(
        samsarix_core.ToolRateLimit(calls=1, period_seconds=1).burst_capacity == 1,
        "rate-limit model behavior differs",
    )
    circuit = samsarix_core.ToolCircuitBreaker(
        failure_threshold=1,
        recovery_timeout_seconds=1,
    )
    _require(circuit.recovery_timeout_seconds == 1.0, "circuit model behavior differs")
    _require(
        samsarix_core.ToolCircuitState.CLOSED.value == "closed",
        "circuit state value differs",
    )
    asyncio.run(verify_runtime())
    print(
        f"{samsarix_core.__version__}: exports, invocation, validation, batch, circuit recovery OK"
    )


async def verify_runtime() -> None:
    """Exercise actual sync/async calls, validation and a failure/recovery lifecycle."""

    @samsarix_core.samsarix_tool(read_only=True)
    def echo(value: str) -> str:
        """Echo one bounded text value."""
        return value

    executions = 0
    available = False

    @samsarix_core.samsarix_tool(read_only=True)
    async def dependency() -> str:
        """Probe a deterministic fake dependency."""
        nonlocal executions
        executions += 1
        if not available:
            raise ConnectionError("private-smoke-secret")
        return "recovered"

    runtime = samsarix_core.ToolRuntime(max_concurrency=2)
    runtime.register(echo)
    runtime.register(
        dependency,
        circuit_breaker=samsarix_core.ToolCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=1,
        ),
    )
    try:
        value = "caf\u00e9-\u6771\u4eac-\U0001f680\nsecond line"
        echoed = await runtime.invoke("echo", {"value": value})
        _require(echoed.success and echoed.output == value, "sync Unicode echo failed")
        invalid = await runtime.invoke("echo", {"value": 42})
        _require(
            invalid.status is samsarix_core.ToolStatus.INVALID_ARGUMENTS,
            "invalid input was not rejected",
        )
        for timeout in (float("nan"), float("inf"), 10**1000):
            invalid_deadline = await runtime.invoke("echo", {"value": value}, timeout=timeout)
            _require(
                invalid_deadline.status is samsarix_core.ToolStatus.INVALID_ARGUMENTS
                and invalid_deadline.error is not None
                and invalid_deadline.error.code == "invalid_timeout",
                "invalid deadline was not rejected",
            )
        batch = await runtime.invoke_many(
            [samsarix_core.ToolCall("echo", {"value": item}) for item in ("first", "second")]
        )
        _require(
            len(batch) == 2
            and all(item.success for item in batch)
            and [item.output for item in batch] == ["first", "second"],
            "ordered batch failed",
        )
        mixed_batch = await runtime.invoke_many(
            [
                samsarix_core.ToolCall("echo", {"value": "invalid"}, timeout=10**1000),
                samsarix_core.ToolCall("echo", {"value": "accepted"}),
            ]
        )
        _require(
            len(mixed_batch) == 2
            and mixed_batch[0].status is samsarix_core.ToolStatus.INVALID_ARGUMENTS
            and mixed_batch[1].success
            and mixed_batch[1].output == "accepted",
            "invalid deadline disrupted a batch",
        )
        failed = await runtime.invoke("dependency", {})
        _require(failed.status is samsarix_core.ToolStatus.FAILED, "failure was not structured")
        _require("private-smoke-secret" not in str(failed.to_dict()), "failure leaked content")
        blocked = await runtime.invoke("dependency", {})
        _require(
            blocked.status is samsarix_core.ToolStatus.CIRCUIT_OPEN and executions == 1,
            "open circuit did not suppress execution",
        )
        details = blocked.error.details if blocked.error is not None else None
        delay = details.get("retry_after_ms") if details is not None else None
        if isinstance(delay, bool) or not isinstance(delay, int) or not 1 <= delay <= 1_001:
            raise RuntimeError("circuit did not supply a bounded retry delay")
        available = True
        await asyncio.sleep(delay / 1_000 + 0.01)
        recovered = await runtime.invoke("dependency", {})
        _require(
            recovered.success and recovered.output == "recovered" and executions == 2,
            "recovery probe failed",
        )
        _require(
            runtime.circuit_state("dependency") is samsarix_core.ToolCircuitState.CLOSED,
            "successful probe did not close the circuit",
        )
        metrics = runtime.metrics()
        _require(
            (metrics.failed, metrics.circuit_open, metrics.circuit_breaker_trips) == (1, 1, 1),
            "circuit accounting differs",
        )
    finally:
        _require(await runtime.aclose(wait_for_sync=True, timeout=5), "runtime did not quiesce")

    await verify_input_boundaries()


async def verify_input_boundaries() -> None:
    """Check derived-error bounds and numeric isolation on the installed wheel."""

    @samsarix_core.samsarix_tool(read_only=True)
    async def number(value: float) -> float:
        """Return a finite number."""
        return value

    @samsarix_core.samsarix_tool(read_only=True)
    async def inspect_rows(payload: dict[str, _SmokeRow]) -> int:
        """Count validated rows."""
        return len(payload)

    async with samsarix_core.ToolRuntime(max_pending_invocations=1) as runtime:
        runtime.register(number)
        runtime.register(inspect_rows)
        batch = await runtime.invoke_many(
            [
                samsarix_core.ToolCall("number", {"value": 10**1000}),
                samsarix_core.ToolCall("number", {"value": 7}),
            ]
        )
        _require(
            len(batch) == 2
            and batch[0].status is samsarix_core.ToolStatus.INVALID_ARGUMENTS
            and batch[1].success
            and batch[1].output == 7.0,
            "numeric overflow disrupted a batch",
        )
        invalid = await runtime.invoke(
            "inspect_rows", {"payload": {"k" * 4096: {f"x{i}": 0 for i in range(128)}}}
        )
        details = invalid.error.details if invalid.error is not None else None
        issues = details.get("issues") if details is not None else None
        _require(
            invalid.status is samsarix_core.ToolStatus.INVALID_ARGUMENTS
            and isinstance(issues, list)
            and 0 < len(issues) <= 64
            and all(
                isinstance(issue, dict)
                and isinstance(issue.get("path"), str)
                and len(str(issue["path"])) <= 128
                and isinstance(issue.get("message"), str)
                and len(str(issue["message"])) <= 128
                for issue in issues
            )
            and isinstance(issues[-1], dict)
            and issues[-1].get("code") == "issues_truncated",
            "validation diagnostics are not bounded",
        )


if __name__ == "__main__":
    main()
