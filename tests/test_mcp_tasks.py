# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import json
import math

import pytest

from samsarix_core import (
    MCPServer,
    ToolCircuitBreaker,
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolRateLimit,
    ToolRuntime,
    report_progress,
    samsarix_tool,
)
from samsarix_core.mcp import MCP_PROTOCOL_VERSION


async def initialize(server: MCPServer, *, version: str = MCP_PROTOCOL_VERSION) -> dict:
    response = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": "initialize",
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "task-tests", "version": "1"},
            },
        }
    )
    assert response is not None
    await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


async def request(
    server: MCPServer,
    request_id: str,
    method: str,
    params: dict,
    *,
    sender=None,
) -> dict:
    response = await server.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params},
        notification_sender=sender,
    )
    assert response is not None
    return response


def task_id(created: dict) -> str:
    value = created["result"]["task"]["taskId"]
    assert isinstance(value, str)
    return value


@pytest.mark.asyncio
async def test_tasks_are_opt_in_negotiated_and_declared_per_tool() -> None:
    @samsarix_tool(task_support="optional")
    async def optional_job(value: str) -> str:
        """Return through normal or task-augmented execution."""

        return value

    @samsarix_tool(task_support="required")
    async def required_job() -> str:
        """Require deferred result retrieval when tasks are negotiated."""

        return "required"

    @samsarix_tool
    def ordinary_job() -> str:
        """Remain unavailable for task augmentation."""

        return "ordinary"

    runtime = ToolRuntime()
    for function in (optional_job, required_job, ordinary_job):
        runtime.register(function)
    server = MCPServer(runtime, enable_tasks=True)
    try:
        initialized = await initialize(server)
        catalog = await request(server, "catalog", "tools/list", {})
        listed = {item["name"]: item for item in catalog["result"]["tools"]}
        normal = await request(
            server,
            "normal",
            "tools/call",
            {"name": "optional_job", "arguments": {"value": "direct"}},
        )
        forbidden = await request(
            server,
            "forbidden",
            "tools/call",
            {"name": "ordinary_job", "arguments": {}, "task": {}},
        )
        required = await request(
            server,
            "required",
            "tools/call",
            {"name": "required_job", "arguments": {}},
        )
        unlisted = await request(server, "list", "tasks/list", {})
    finally:
        await server.aclose()

    assert initialized["result"]["capabilities"] == {
        "tools": {"listChanged": False},
        "tasks": {"cancel": {}, "requests": {"tools": {"call": {}}}},
    }
    assert listed["optional_job"]["execution"] == {"taskSupport": "optional"}
    assert listed["required_job"]["execution"] == {"taskSupport": "required"}
    assert listed["ordinary_job"]["execution"] == {"taskSupport": "forbidden"}
    assert normal["result"]["structuredContent"] == {"result": "direct"}
    assert forbidden["error"]["code"] == -32601
    assert required["error"]["code"] == -32601
    assert unlisted["error"] == {"code": -32601, "message": "Unknown method 'tasks/list'"}


@pytest.mark.asyncio
async def test_older_clients_keep_normal_calls_and_ignore_task_augmentation() -> None:
    @samsarix_tool(task_support="required")
    async def legacy_compatible() -> str:
        """Run normally when the negotiated protocol has no task capability."""

        return "direct"

    runtime = ToolRuntime()
    runtime.register(legacy_compatible)
    server = MCPServer(runtime, enable_tasks=True)
    try:
        initialized = await initialize(server, version="2025-06-18")
        catalog = await request(server, "catalog", "tools/list", {})
        called = await request(
            server,
            "call",
            "tools/call",
            {"name": "legacy_compatible", "arguments": {}, "task": "ignored"},
        )
        unavailable = await request(server, "get", "tasks/get", {"taskId": "missing"})
    finally:
        await server.aclose()

    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert "execution" not in catalog["result"]["tools"][0]
    assert called["result"]["structuredContent"] == {"result": "direct"}
    assert unavailable["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_task_success_progress_logging_and_blocking_result() -> None:
    release = asyncio.Event()
    notifications: list[dict] = []

    @samsarix_tool(task_support="optional")
    async def export_records(batch: str) -> dict[str, str]:
        """Wait for a release and return one content-safe export marker."""

        assert await report_progress(1, total=2, message="accepted")
        await release.wait()
        assert await report_progress(2, total=2, message="completed")
        return {"batch": batch}

    async def collect(message: dict) -> None:
        notifications.append(message)

    runtime = ToolRuntime()
    runtime.register(export_records)
    server = MCPServer(
        runtime,
        enable_tasks=True,
        enable_logging=True,
        default_log_level="info",
        default_task_ttl_ms=2_000,
        max_task_ttl_ms=2_000,
        task_poll_interval_ms=25,
    )
    try:
        await initialize(server)
        created = await request(
            server,
            "create",
            "tools/call",
            {
                "name": "export_records",
                "arguments": {"batch": "private-batch"},
                "task": {"ttl": 50_000},
                "_meta": {"progressToken": "progress"},
            },
            sender=collect,
        )
        identifier = task_id(created)
        state = created["result"]["task"]
        working = await request(server, "get-working", "tasks/get", {"taskId": identifier})
        waiting = asyncio.create_task(
            request(server, "result", "tasks/result", {"taskId": identifier})
        )
        await asyncio.sleep(0)
        assert not waiting.done()
        release.set()
        result = await asyncio.wait_for(waiting, timeout=1)
        completed = await request(server, "get-done", "tasks/get", {"taskId": identifier})
        terminal_cancel = await request(
            server, "cancel-done", "tasks/cancel", {"taskId": identifier}
        )
    finally:
        release.set()
        await server.aclose()

    assert len(identifier) == 32
    int(identifier, 16)
    assert state["status"] == "working"
    assert state["ttl"] == 2_000
    assert state["pollInterval"] == 25
    assert "private-batch" not in json.dumps(state)
    assert created["result"]["_meta"] == {
        "io.modelcontextprotocol/related-task": {"taskId": identifier}
    }
    assert working["result"]["status"] == "working"
    assert result["result"]["structuredContent"] == {"batch": "private-batch"}
    assert result["result"]["_meta"]["io.modelcontextprotocol/related-task"] == {
        "taskId": identifier
    }
    assert completed["result"]["status"] == "completed"
    assert terminal_cancel["error"]["code"] == -32602
    progress = [item for item in notifications if item["method"] == "notifications/progress"]
    logs = [item for item in notifications if item["method"] == "notifications/message"]
    assert [item["params"]["progress"] for item in progress] == [1.0, 2.0]
    for notification in progress + logs:
        assert notification["params"]["_meta"] == {
            "io.modelcontextprotocol/related-task": {"taskId": identifier}
        }


@pytest.mark.asyncio
async def test_failed_and_cancelled_tasks_have_safe_terminal_results() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()

    @samsarix_tool(task_support="optional")
    async def fail_job(secret: str) -> str:
        """Fail without returning private exception content."""

        raise RuntimeError(f"must-not-leak:{secret}")

    @samsarix_tool(task_support="optional", timeout=5)
    async def wait_job() -> str:
        """Remain active until task cancellation."""

        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return "unreachable"

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(fail_job)
    runtime.register(wait_job)
    server = MCPServer(runtime, enable_tasks=True, default_task_ttl_ms=1_000)
    try:
        await initialize(server)
        failed_create = await request(
            server,
            "fail-create",
            "tools/call",
            {
                "name": "fail_job",
                "arguments": {"secret": "private"},
                "task": {},
            },
        )
        failed_id = task_id(failed_create)
        failed_result = await request(server, "fail-result", "tasks/result", {"taskId": failed_id})
        failed_state = await request(server, "fail-get", "tasks/get", {"taskId": failed_id})

        wait_create = await request(
            server,
            "wait-create",
            "tools/call",
            {"name": "wait_job", "arguments": {}, "task": {}},
        )
        wait_id = task_id(wait_create)
        await asyncio.wait_for(started.wait(), timeout=1)
        cancelled = await request(server, "cancel", "tasks/cancel", {"taskId": wait_id})
        await asyncio.wait_for(stopped.wait(), timeout=1)
        cancel_result = await request(server, "cancel-result", "tasks/result", {"taskId": wait_id})
        duplicate = await request(server, "cancel-again", "tasks/cancel", {"taskId": wait_id})
    finally:
        await server.aclose()

    encoded_failure = json.dumps({"state": failed_state, "result": failed_result})
    assert failed_state["result"]["status"] == "failed"
    assert failed_result["result"]["isError"] is True
    assert "private" not in encoded_failure
    assert "must-not-leak" not in encoded_failure
    assert cancelled["result"]["status"] == "cancelled"
    assert cancel_result["result"]["isError"] is True
    assert cancel_result["result"]["_meta"]["com.samsarix/status"] == "cancelled"
    assert duplicate["error"]["code"] == -32602
    assert runtime.metrics().cancelled == 1


@pytest.mark.asyncio
async def test_task_capacity_expiry_and_invalid_requests_are_bounded() -> None:
    never = asyncio.Event()

    @samsarix_tool(task_support="optional", timeout=5)
    async def bounded_job() -> str:
        """Wait beyond the deliberately short retention lifetime."""

        await never.wait()
        return "unreachable"

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(bounded_job)
    server = MCPServer(
        runtime,
        enable_tasks=True,
        max_retained_tasks=1,
        default_task_ttl_ms=30,
        max_task_ttl_ms=50,
        task_poll_interval_ms=5,
    )
    try:
        await initialize(server)
        invalid_ttls = []
        for index, value in enumerate((True, 0, -1, math.inf, "long")):
            invalid_ttls.append(
                await request(
                    server,
                    f"invalid-{index}",
                    "tools/call",
                    {"name": "bounded_job", "arguments": {}, "task": {"ttl": value}},
                )
            )
        malformed = await request(
            server,
            "malformed",
            "tools/call",
            {"name": "bounded_job", "arguments": {}, "task": None},
        )
        cyclic: dict = {}
        cyclic["self"] = cyclic
        unsafe = await request(
            server,
            "unsafe",
            "tools/call",
            {"name": "bounded_job", "arguments": cyclic, "task": {}},
        )
        unknown = await request(
            server,
            "unknown",
            "tools/call",
            {"name": "missing", "arguments": {}, "task": {}},
        )
        created = await request(
            server,
            "first",
            "tools/call",
            {"name": "bounded_job", "arguments": {}, "task": {"ttl": 30}},
        )
        identifier = task_id(created)
        full = await request(
            server,
            "full",
            "tools/call",
            {"name": "bounded_job", "arguments": {}, "task": {}},
        )
        expired_result = await request(
            server, "expired-result", "tasks/result", {"taskId": identifier}
        )
        missing = await request(server, "missing-get", "tasks/get", {"taskId": identifier})
        replacement = await request(
            server,
            "replacement",
            "tools/call",
            {"name": "bounded_job", "arguments": {}, "task": {}},
        )
        bad_task_id = await request(server, "bad-id", "tasks/get", {"taskId": ""})
    finally:
        await server.aclose()

    assert all(item["error"]["code"] == -32602 for item in invalid_ttls)
    assert malformed["error"]["code"] == -32602
    assert unsafe["error"]["code"] == -32602
    assert unknown["error"]["code"] == -32601
    assert full["error"] == {"code": -32000, "message": "Retained MCP task capacity reached"}
    assert expired_result["error"]["code"] == -32602
    assert missing["error"]["code"] == -32602
    assert replacement["result"]["task"]["status"] == "working"
    assert bad_task_id["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_task_result_wait_can_be_request_cancelled_without_cancelling_task() -> None:
    release = asyncio.Event()

    @samsarix_tool(task_support="optional", timeout=5)
    async def resumable_job() -> str:
        """Remain live when only a result-wait request is cancelled."""

        await release.wait()
        return "done"

    runtime = ToolRuntime()
    runtime.register(resumable_job)
    server = MCPServer(runtime, enable_tasks=True, default_task_ttl_ms=1_000)
    try:
        await initialize(server)
        created = await request(
            server,
            "create",
            "tools/call",
            {"name": "resumable_job", "arguments": {}, "task": {}},
        )
        identifier = task_id(created)
        waiter = asyncio.create_task(
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "waiter",
                    "method": "tasks/result",
                    "params": {"taskId": identifier},
                }
            )
        )
        await asyncio.sleep(0)
        await server.handle(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "waiter"},
            }
        )
        assert await asyncio.wait_for(waiter, timeout=1) is None
        working = await request(server, "working", "tasks/get", {"taskId": identifier})
        release.set()
        completed = await request(server, "completed", "tasks/result", {"taskId": identifier})
    finally:
        release.set()
        await server.aclose()

    assert working["result"]["status"] == "working"
    assert completed["result"]["structuredContent"] == {"result": "done"}


@pytest.mark.asyncio
async def test_background_notification_failure_becomes_a_safe_failed_task() -> None:
    @samsarix_tool(task_support="optional")
    async def reporting_job() -> str:
        """Exercise a failed task-owned progress transport."""

        await report_progress(1)
        return "unexpected"

    async def broken_sender(message: dict) -> None:
        raise OSError("private transport detail")

    runtime = ToolRuntime()
    runtime.register(reporting_job)
    server = MCPServer(runtime, enable_tasks=True)
    try:
        await initialize(server)
        created = await request(
            server,
            "create",
            "tools/call",
            {
                "name": "reporting_job",
                "arguments": {},
                "task": {},
                "_meta": {"progressToken": "broken"},
            },
            sender=broken_sender,
        )
        result = await request(server, "result", "tasks/result", {"taskId": task_id(created)})
    finally:
        await server.aclose()

    encoded = json.dumps(result)
    assert result["result"]["isError"] is True
    assert "task_execution_failed" in encoded
    assert "private transport detail" not in encoded


@pytest.mark.asyncio
async def test_task_policy_denial_retains_only_a_safe_failed_result() -> None:
    executed = False

    @samsarix_tool(task_support="optional", destructive=True)
    async def publish_private_record(record_id: str) -> str:
        """Publish only after the host policy allows this record."""

        nonlocal executed
        executed = True
        return record_id

    async def deny_policy(context: ToolPolicyContext) -> ToolPolicyDecision:
        assert context.arguments["record_id"] == "private-record"
        return ToolPolicyDecision.DENY

    runtime = ToolRuntime(policy=deny_policy)
    runtime.register(publish_private_record)
    server = MCPServer(runtime, enable_tasks=True)
    try:
        await initialize(server)
        created = await request(
            server,
            "create-denied",
            "tools/call",
            {
                "name": "publish_private_record",
                "arguments": {"record_id": "private-record"},
                "task": {},
            },
        )
        identifier = task_id(created)
        result = await request(server, "result-denied", "tasks/result", {"taskId": identifier})
        state = await request(server, "state-denied", "tasks/get", {"taskId": identifier})
    finally:
        await server.aclose()

    assert state["result"]["status"] == "failed"
    assert result["result"]["isError"] is True
    assert result["result"]["_meta"] == {
        "com.samsarix/invocation-id": result["result"]["_meta"]["com.samsarix/invocation-id"],
        "com.samsarix/status": "denied",
        "com.samsarix/duration-ms": result["result"]["_meta"]["com.samsarix/duration-ms"],
        "io.modelcontextprotocol/related-task": {"taskId": identifier},
    }
    assert json.loads(result["result"]["content"][0]["text"])["error"] == {
        "code": "tool_denied",
        "message": "Tool invocation was denied by host policy",
        "retryable": False,
    }
    assert executed is False
    assert runtime.metrics().denied == 1
    assert "private-record" not in json.dumps([created, state, result])


@pytest.mark.asyncio
async def test_task_rate_limit_retains_retryable_safe_terminal_result() -> None:
    executions: list[str] = []

    @samsarix_tool(task_support="optional")
    async def quota_job(value: str) -> str:
        """Represent a task-wrapped call to a rate-constrained API."""

        executions.append(value)
        return value

    runtime = ToolRuntime()
    runtime._rate_limit_clock = lambda: 15.0
    runtime.register(
        quota_job,
        rate_limit=ToolRateLimit(calls=1, period_seconds=20),
    )
    server = MCPServer(runtime, enable_tasks=True)
    try:
        await initialize(server)
        first_create = await request(
            server,
            "create-first-quota",
            "tools/call",
            {"name": "quota_job", "arguments": {"value": "first"}, "task": {}},
        )
        first_result = await request(
            server,
            "result-first-quota",
            "tasks/result",
            {"taskId": task_id(first_create)},
        )
        limited_create = await request(
            server,
            "create-limited-quota",
            "tools/call",
            {
                "name": "quota_job",
                "arguments": {"value": "private-task-rate-value"},
                "task": {},
            },
        )
        identifier = task_id(limited_create)
        limited_result = await request(
            server,
            "result-limited-quota",
            "tasks/result",
            {"taskId": identifier},
        )
        limited_state = await request(
            server,
            "state-limited-quota",
            "tasks/get",
            {"taskId": identifier},
        )
    finally:
        await server.aclose()

    assert first_result["result"]["isError"] is False
    assert limited_state["result"]["status"] == "failed"
    assert limited_result["result"]["isError"] is True
    assert limited_result["result"]["_meta"]["com.samsarix/status"] == "rate_limited"
    assert json.loads(limited_result["result"]["content"][0]["text"])["error"] == {
        "code": "tool_rate_limited",
        "message": "Tool invocation rate limit is temporarily exhausted",
        "retryable": True,
        "details": {"retry_after_ms": 20000},
    }
    assert executions == ["first"]
    assert runtime.metrics().rate_limited == 1
    assert "private-task-rate-value" not in json.dumps(
        [limited_create, limited_state, limited_result]
    )


@pytest.mark.asyncio
async def test_task_open_circuit_retains_retryable_safe_terminal_result() -> None:
    executions: list[str] = []

    @samsarix_tool(task_support="optional")
    async def unstable_job(value: str) -> str:
        """Represent a task-wrapped call to a circuit-protected dependency."""

        executions.append(value)
        raise RuntimeError("private task dependency failure")

    runtime = ToolRuntime()
    runtime._circuit_clock = lambda: 20.0
    runtime.register(
        unstable_job,
        circuit_breaker=ToolCircuitBreaker(
            failure_threshold=1,
            recovery_timeout_seconds=25,
        ),
    )
    server = MCPServer(runtime, enable_tasks=True)
    try:
        await initialize(server)
        failed_create = await request(
            server,
            "create-failing-circuit",
            "tools/call",
            {"name": "unstable_job", "arguments": {"value": "first"}, "task": {}},
        )
        failed_result = await request(
            server,
            "result-failing-circuit",
            "tasks/result",
            {"taskId": task_id(failed_create)},
        )
        blocked_create = await request(
            server,
            "create-blocked-circuit",
            "tools/call",
            {
                "name": "unstable_job",
                "arguments": {"value": "private-task-circuit-value"},
                "task": {},
            },
        )
        identifier = task_id(blocked_create)
        blocked_result = await request(
            server,
            "result-blocked-circuit",
            "tasks/result",
            {"taskId": identifier},
        )
        blocked_state = await request(
            server,
            "state-blocked-circuit",
            "tasks/get",
            {"taskId": identifier},
        )
    finally:
        await server.aclose()

    assert failed_result["result"]["isError"] is True
    assert blocked_state["result"]["status"] == "failed"
    assert blocked_result["result"]["isError"] is True
    assert blocked_result["result"]["_meta"]["com.samsarix/status"] == "circuit_open"
    assert json.loads(blocked_result["result"]["content"][0]["text"])["error"] == {
        "code": "tool_circuit_open",
        "message": "Tool dependency circuit is temporarily open",
        "retryable": True,
        "details": {"retry_after_ms": 25000},
    }
    assert executions == ["first"]
    assert runtime.metrics().circuit_breaker_trips == 1
    assert runtime.metrics().circuit_open == 1
    assert "private-task-circuit-value" not in json.dumps(
        [blocked_create, blocked_state, blocked_result]
    )


def test_task_configuration_and_metadata_validation() -> None:
    with pytest.raises(ValueError, match="task_support"):

        @samsarix_tool(task_support="sometimes")  # type: ignore[arg-type]
        def invalid_support() -> str:
            """Reject an unknown task support mode."""

            return "no"

    runtime = ToolRuntime()
    try:
        with pytest.raises(TypeError, match="enable_tasks"):
            MCPServer(runtime, enable_tasks=1)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="max_tasks"):
            MCPServer(runtime, max_retained_tasks=True)
        with pytest.raises(ValueError, match="max_tasks"):
            MCPServer(runtime, max_retained_tasks=0)
        with pytest.raises(ValueError, match="cannot exceed"):
            MCPServer(runtime, default_task_ttl_ms=2, max_task_ttl_ms=1)
        with pytest.raises(TypeError, match="close_runtime"):
            asyncio.run(MCPServer(runtime).aclose(close_runtime=1))  # type: ignore[arg-type]
    finally:
        asyncio.run(runtime.aclose())


@pytest.mark.parametrize(
    "field", ["default_task_ttl_ms", "max_task_ttl_ms", "task_poll_interval_ms"]
)
def test_task_duration_configuration_rejects_float_overflow(field):
    runtime = ToolRuntime()
    try:
        with pytest.raises(ValueError, match="finite"):
            MCPServer(runtime, **{field: 10**1000})
    finally:
        asyncio.run(runtime.aclose())


@pytest.mark.parametrize(
    "ttl",
    [
        pytest.param(10**1000, id="overflowing-integer"),
        pytest.param(-(10**1000), id="negative-overflowing-integer"),
        pytest.param(math.nan, id="nan"),
        pytest.param(math.inf, id="infinity"),
    ],
)
async def test_invalid_task_ttl_keeps_protocol_and_retention_capacity_available(ttl):
    executed = []

    @samsarix_tool(task_support="optional")
    async def echo(value: str) -> str:
        """Execute only after task metadata has been validated."""

        executed.append(value)
        return value

    runtime = ToolRuntime()
    runtime.register(echo)
    server = MCPServer(runtime, enable_tasks=True, max_retained_tasks=1)
    try:
        await initialize(server)
        bad = await request(
            server,
            "request",
            "tools/call",
            {"name": "echo", "arguments": {"value": "private-ttl-input"}, "task": {"ttl": ttl}},
        )
        assert bad["error"]["code"] == -32602
        assert "finite" in bad["error"]["message"]
        assert "private-ttl-input" not in json.dumps(bad, allow_nan=False)
        assert executed == [] and runtime.metrics().calls_total == 0
        # Reuse the protocol request ID and the sole retained-task slot. A very
        # large but representable TTL must still clamp to the configured maximum.
        good = await request(
            server,
            "request",
            "tools/call",
            {"name": "echo", "arguments": {"value": "accepted"}, "task": {"ttl": 1e308}},
        )
        assert good["result"]["task"]["ttl"] == 3_600_000
        result = await request(server, "result", "tasks/result", {"taskId": task_id(good)})
        assert result["result"]["structuredContent"] == {"result": "accepted"}
        assert executed == ["accepted"]
    finally:
        await server.aclose()
