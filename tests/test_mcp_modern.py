# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import copy
import io
import json

import pytest

from samsarix_core import MCPServer, ToolRuntime, report_progress, samsarix_tool, serve_stdio

VERSION = "2026-07-28"
PREFIX = "io.modelcontextprotocol/"


def request(method="tools/list", *, identifier=1, params=None, meta=None):
    return {
        "jsonrpc": "2.0",
        "id": identifier,
        "method": method,
        "params": {
            **(params or {}),
            "_meta": {
                PREFIX + "protocolVersion": VERSION,
                PREFIX + "clientCapabilities": {},
                **(meta or {}),
            },
        },
    }


def legacy_initialize():
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {}},
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("modern_after_ping", [False, True])
async def test_unversioned_preinitialize_ping_preserves_both_protocol_choices(modern_after_ping):
    async with ToolRuntime() as runtime:
        server = MCPServer(runtime, enable_modern=True)
        assert await server.handle({"jsonrpc": "2.0", "id": "ping", "method": "ping"}) == {
            "jsonrpc": "2.0",
            "id": "ping",
            "result": {},
        }
        if modern_after_ping:
            assert (await server.handle(request("server/discover")))["result"][
                "supportedVersions"
            ] == [VERSION]
            # With modern metadata, ping is still a removed method.
            assert (await server.handle(request("ping")))["error"]["code"] == -32601
        else:
            assert (await server.handle(legacy_initialize()))["result"][
                "protocolVersion"
            ] == "2025-11-25"


@samsarix_tool(read_only=True, open_world=False)
def echo(value: str) -> str:
    """Return one local string."""
    return value


@samsarix_tool(task_support="required")
async def legacy_task() -> str:
    """A deliberately legacy-task-only tool."""
    raise AssertionError("Must not run through modern MCP")


@pytest.mark.asyncio
async def test_modern_discovery_catalog_and_call_without_handshake():
    async with ToolRuntime() as runtime:
        runtime.register(legacy_task)
        runtime.register(echo)
        server = MCPServer(
            runtime, enable_modern=True, enable_tasks=True, instructions="Local only."
        )
        discovery = await server.handle(request("server/discover"))
        assert discovery["result"] == {
            "resultType": "complete",
            "supportedVersions": [VERSION],
            "capabilities": {"tools": {"listChanged": False}},
            "ttlMs": 0,
            "cacheScope": "private",
            "instructions": "Local only.",
            "_meta": {
                PREFIX
                + "serverInfo": {
                    "name": "samsarix-core",
                    "title": "Samsarix Core",
                    "version": server.version,
                    "websiteUrl": "https://samsarix.com",
                }
            },
        }
        catalog = (await server.handle(request()))["result"]
        assert catalog["resultType"] == "complete"
        assert catalog["ttlMs"] == 0 and catalog["cacheScope"] == "private"
        assert [tool["name"] for tool in catalog["tools"]] == ["echo"]
        assert "execution" not in catalog["tools"][0]
        assert catalog["tools"][0]["outputSchema"]["properties"]["result"]["type"] == "string"
        call = request("tools/call", params={"name": "echo", "arguments": {"value": "café\n東京"}})
        before = copy.deepcopy(call)
        result = (await server.handle(call))["result"]
        assert result["resultType"] == "complete"
        assert result["structuredContent"] == {"result": "café\n東京"}
        assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
        assert PREFIX + "serverInfo" in result["_meta"]
        assert call == before


@pytest.mark.asyncio
async def test_modern_direct_first_call_and_catalog_order_are_request_independent():
    @samsarix_tool
    def zebra(value: str) -> str:
        """Return a value."""
        return value

    @samsarix_tool
    def alpha(value: str) -> str:
        """Return a value."""
        return value

    async with ToolRuntime() as runtime:
        runtime.register(zebra)
        runtime.register(alpha)
        server = MCPServer(runtime, enable_modern=True)
        result = await server.handle(
            request("tools/call", params={"name": "alpha", "arguments": {"value": "ok"}})
        )
        assert result["result"]["structuredContent"] == {"result": "ok"}
        first = await server.handle(
            request(
                meta={PREFIX + "clientCapabilities": {"extensions": {"example.test/private": {}}}}
            )
        )
        second = await server.handle(request())
        assert first == second
        assert [tool["name"] for tool in first["result"]["tools"]] == ["alpha", "zebra"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        (None, None),
        ("protocolVersion", None),
        ("protocolVersion", 2),
        ("clientCapabilities", None),
        ("clientCapabilities", []),
        ("logLevel", None),
        ("logLevel", "secret"),
        ("logLevel", {}),
    ],
)
async def test_modern_rejects_malformed_metadata_before_any_execution(field, value):
    async with ToolRuntime() as runtime:
        runtime.register(echo)
        server = MCPServer(runtime, enable_modern=True)
        await server.handle(request("server/discover"))
        call = request("tools/call", params={"name": "echo", "arguments": {"value": "private"}})
        if field is None:
            del call["params"]["_meta"]
        else:
            call["params"]["_meta"][PREFIX + field] = value
        response = await server.handle(call)
        assert response["error"]["code"] == -32602
        assert "private" not in str(response) and "secret" not in str(response)
        assert runtime.metrics().calls_total == 0
        assert (await server.handle(request()))["result"]["resultType"] == "complete"


@pytest.mark.asyncio
async def test_modern_version_retry_does_not_initialize_or_execute():
    async with ToolRuntime() as runtime:
        runtime.register(echo)
        server = MCPServer(runtime, enable_modern=True)
        response = await server.handle(
            request(
                "tools/call",
                params={"name": "echo"},
                meta={PREFIX + "protocolVersion": "2099-01-01"},
            )
        )
        assert response["error"] == {
            "code": -32022,
            "message": "Unsupported protocol version",
            "data": {"supported": [VERSION], "requested": "2099-01-01"},
        }
        assert runtime.metrics().calls_total == 0
        assert (await server.handle(request()))["result"]["resultType"] == "complete"


@pytest.mark.asyncio
async def test_modern_missing_metadata_cursors_and_unknown_tools_recover():
    async with ToolRuntime() as runtime:
        server = MCPServer(runtime, enable_modern=True)
        await server.handle(request("server/discover"))
        malformed = legacy_initialize()
        del malformed["params"]["protocolVersion"]
        assert (await server.handle(malformed))["error"]["code"] == -32602
        malformed["params"]["protocolVersion"] = VERSION
        assert (await server.handle(malformed))["error"]["code"] == -32601
        assert (await server.handle(request(params={"cursor": "private"})))["error"][
            "code"
        ] == -32602
        missing = await server.handle(request("tools/call", params={"name": "missing"}))
        assert missing["result"]["isError"] is True
        assert missing["result"]["resultType"] == "complete"
        assert (await server.handle(request()))["result"]["tools"] == []
        assert (await server.handle(legacy_initialize()))["error"]["data"]["supported"] == [VERSION]
        assert (await server.handle(request()))["result"]["resultType"] == "complete"


@pytest.mark.asyncio
async def test_opt_in_keeps_legacy_handshake_and_tasks_separate():
    async with ToolRuntime() as runtime:
        runtime.register(legacy_task)
        server = MCPServer(runtime, enable_modern=True, enable_tasks=True)
        initialized = await server.handle(legacy_initialize())
        assert initialized["result"]["protocolVersion"] == "2025-11-25"
        await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        modern = await server.handle(request("server/discover"))
        assert modern["error"]["code"] == -32022
        assert modern["error"]["data"]["supported"] == ["2025-11-25", "2025-06-18"]
        catalog = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        assert catalog["result"]["tools"][0]["execution"] == {"taskSupport": "required"}
        assert "resultType" not in catalog["result"]
        same_version = await server.handle(request(meta={PREFIX + "protocolVersion": "2025-11-25"}))
        assert same_version["error"]["code"] == -32602


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method",
    [
        "ping",
        "logging/setLevel",
        "tasks/get",
        "tasks/result",
        "tasks/cancel",
        "subscriptions/listen",
        "resources/list",
        "prompts/list",
    ],
)
async def test_modern_does_not_emulate_removed_or_unimplemented_methods(method):
    async with ToolRuntime() as runtime:
        server = MCPServer(runtime, enable_modern=True, enable_tasks=True, enable_logging=True)
        result = await server.handle(request(method))
        assert result["error"]["code"] == -32601
        assert "result" not in result


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["task", "inputResponses", "requestState"])
async def test_modern_rejects_unsupported_execution_forms_before_invocation(field):
    async with ToolRuntime() as runtime:
        runtime.register(echo)
        server = MCPServer(runtime, enable_modern=True)
        response = await server.handle(
            request(
                "tools/call", params={"name": "echo", "arguments": {"value": "private"}, field: {}}
            )
        )
        assert response["error"]["code"] == -32602
        assert runtime.metrics().calls_total == 0


@pytest.mark.asyncio
async def test_modern_required_task_tool_cannot_be_invoked_by_name():
    async with ToolRuntime() as runtime:
        runtime.register(legacy_task)
        server = MCPServer(runtime, enable_modern=True, enable_tasks=True)
        response = await server.handle(request("tools/call", params={"name": "legacy_task"}))
        assert response["error"]["code"] == -32601
        assert runtime.metrics().calls_total == 0


@pytest.mark.asyncio
async def test_modern_logs_are_opt_in_per_request_even_when_calls_overlap():
    entered = asyncio.Event()
    finish = asyncio.Event()

    @samsarix_tool
    async def delayed(value: str) -> str:
        """Wait for the overlapping call to finish."""
        entered.set()
        await finish.wait()
        return value

    async with ToolRuntime() as runtime:
        runtime.register(delayed)
        runtime.register(echo)
        server = MCPServer(
            runtime, enable_modern=True, enable_logging=True, default_log_level="debug"
        )
        notifications = []

        async def collect(notification):
            notifications.append(notification)

        first = asyncio.create_task(
            server.handle(
                request(
                    "tools/call",
                    identifier="slow",
                    params={"name": "delayed", "arguments": {"value": "private"}},
                    meta={PREFIX + "logLevel": "info"},
                ),
                notification_sender=collect,
            )
        )
        try:
            await asyncio.wait_for(entered.wait(), 1)
            for index, level in enumerate((None, "emergency", "info")):
                await server.handle(
                    request(
                        "tools/call",
                        identifier=index,
                        params={"name": "echo", "arguments": {"value": "private"}},
                        meta={} if level is None else {PREFIX + "logLevel": level},
                    ),
                    notification_sender=collect,
                )
            assert len(notifications) == 1
            finish.set()
            await asyncio.wait_for(first, 1)
            assert len(notifications) == 2
            assert [note["params"]["data"]["tool"] for note in notifications] == ["echo", "delayed"]
            assert "private" not in str(notifications)
            # A previous request's level must not enable this error log.
            failure = await server.handle(
                request(
                    "tools/call",
                    params={"name": "echo", "arguments": {"value": {"secret": "private"}}},
                ),
                notification_sender=collect,
            )
            assert failure["result"]["isError"] is True
            assert failure["result"]["resultType"] == "complete"
            assert "private" not in str(failure)
            assert len(notifications) == 2
        finally:
            finish.set()
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)


@pytest.mark.asyncio
async def test_modern_cancellation_stops_notifications_and_recovers_capacity():
    started = asyncio.Event()
    stopped = asyncio.Event()

    @samsarix_tool
    async def wait() -> str:
        """Wait for client cancellation."""
        try:
            await report_progress(1, total=2, message="started")
            started.set()
            await asyncio.Event().wait()
        finally:
            stopped.set()
        return "unreachable"

    async with ToolRuntime(max_concurrency=1) as runtime:
        runtime.register(wait)
        runtime.register(echo)
        server = MCPServer(runtime, enable_modern=True, enable_logging=True)
        notes = []

        async def collect(note):
            notes.append(note)

        call = asyncio.create_task(
            server.handle(
                request(
                    "tools/call",
                    identifier="cancel-me",
                    params={"name": "wait"},
                    meta={"progressToken": "actual-progress", PREFIX + "logLevel": "debug"},
                ),
                notification_sender=collect,
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 1)
            for identifier in (True, 1.0, "unknown"):
                await server.handle(
                    {
                        "jsonrpc": "2.0",
                        "method": "notifications/cancelled",
                        "params": {"requestId": identifier},
                    }
                )
            assert not stopped.is_set()
            await server.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": "cancel-me"},
                }
            )
            assert await asyncio.wait_for(call, 1) is None
            assert stopped.is_set()
            assert len(notes) == 1 and notes[0]["params"]["progressToken"] == "actual-progress"
            response = await asyncio.wait_for(
                server.handle(
                    request(
                        "tools/call", params={"name": "echo", "arguments": {"value": "recovered"}}
                    )
                ),
                1,
            )
            assert response["result"]["structuredContent"] == {"result": "recovered"}
            assert runtime.metrics().cancelled == 1
            assert runtime.metrics().in_flight == 0
        finally:
            call.cancel()
            await asyncio.gather(call, return_exceptions=True)


@pytest.mark.asyncio
async def test_modern_stdio_discovery_error_recovery_and_eof():
    async with ToolRuntime() as runtime:
        runtime.register(echo)
        messages = [
            request("server/discover"),
            request("ping", identifier=2),
            request(identifier=3),
            request(
                "tools/call",
                identifier=4,
                params={"name": "echo", "arguments": {"value": "café\n東京"}},
            ),
        ]
        writer = io.StringIO()
        await serve_stdio(
            MCPServer(runtime, enable_modern=True),
            input_stream=io.BytesIO(
                ("\n".join(json.dumps(item) for item in messages) + "\n").encode()
            ),
            output_stream=writer,
            close_runtime=False,
        )
        responses = {item["id"]: item for item in map(json.loads, writer.getvalue().splitlines())}
        assert len(responses) == 4
        assert responses[1]["result"]["supportedVersions"] == [VERSION]
        assert responses[2]["error"]["code"] == -32601
        assert responses[4]["result"]["structuredContent"] == {"result": "café\n東京"}


@pytest.mark.asyncio
async def test_modern_is_explicit_and_ids_are_integral():
    async with ToolRuntime() as runtime:
        with pytest.raises(TypeError, match="enable_modern"):
            MCPServer(runtime, enable_modern="yes")
        default = MCPServer(runtime)
        assert "error" in await default.handle(request("server/discover"))
        server = MCPServer(runtime, enable_modern=True)
        assert (await server.handle(request(identifier=1.5)))["error"]["code"] == -32600
        assert (await server.handle(request()))["result"]["resultType"] == "complete"
