# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import io
import json
from threading import Event
from typing import TypedDict

import pytest

from samsarix_core import (
    MCPServer,
    ProgressHandlerError,
    ToolRuntime,
    report_progress,
    samsarix_tool,
    serve_stdio,
)
from samsarix_core.mcp import MCP_PROTOCOL_VERSION


class InventoryResult(TypedDict):
    sku: str
    available: int


@samsarix_tool(
    title="Look up inventory",
    tags=("inventory", "read"),
    read_only=True,
    open_world=False,
)
def inventory(sku: str) -> InventoryResult:
    """Return local inventory for a stock-keeping unit."""

    return {"sku": sku, "available": 7}


@samsarix_tool(destructive=False, idempotent=True, open_world=False)
def reserve(sku: str, quantity: int) -> str:
    """Reserve local inventory once for an idempotency-controlled request."""

    return f"reserved:{sku}:{quantity}"


@samsarix_tool
def explode(secret: str) -> str:
    """Fail without exposing a secret."""

    raise RuntimeError(f"do-not-expose:{secret}")


def mcp_runtime() -> ToolRuntime:
    runtime = ToolRuntime()
    for function in (inventory, reserve, explode):
        runtime.register(function)
    return runtime


async def initialize(server: MCPServer, *, version: str = MCP_PROTOCOL_VERSION) -> dict:
    response = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": version,
                "capabilities": {},
                "clientInfo": {"name": "tests", "version": "1"},
            },
        }
    )
    assert response is not None
    await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
    return response


@pytest.mark.asyncio
async def test_mcp_lifecycle_and_version_negotiation() -> None:
    runtime = mcp_runtime()
    server = MCPServer(runtime, instructions="Ask before write operations.")
    try:
        early = await server.handle(
            {"jsonrpc": "2.0", "id": "early", "method": "tools/list", "params": {}}
        )
        initialized = await initialize(server, version="2099-01-01")
        ping = await server.handle({"jsonrpc": "2.0", "id": 2, "method": "ping"})
    finally:
        await runtime.aclose()

    assert early == {
        "jsonrpc": "2.0",
        "id": "early",
        "error": {"code": -32002, "message": "Server has not completed MCP initialization"},
    }
    assert initialized["result"]["protocolVersion"] == MCP_PROTOCOL_VERSION
    assert initialized["result"]["capabilities"] == {"tools": {"listChanged": False}}
    assert initialized["result"]["serverInfo"]["name"] == "samsarix-core"
    assert initialized["result"]["instructions"] == "Ask before write operations."
    assert ping == {"jsonrpc": "2.0", "id": 2, "result": {}}


@pytest.mark.asyncio
async def test_mcp_tool_catalog_has_schemas_annotations_and_metadata() -> None:
    runtime = mcp_runtime()
    server = MCPServer(runtime)
    try:
        await initialize(server)
        response = await server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        )
    finally:
        await runtime.aclose()

    assert response is not None
    tools = {tool["name"]: tool for tool in response["result"]["tools"]}
    lookup = tools["inventory"]
    assert lookup["title"] == "Look up inventory"
    assert lookup["inputSchema"]["properties"]["sku"] == {"type": "string"}
    assert lookup["outputSchema"] == {
        "type": "object",
        "properties": {
            "sku": {"type": "string"},
            "available": {"type": "integer"},
        },
        "required": ["sku", "available"],
        "additionalProperties": False,
        "$schema": "https://json-schema.org/draft/2020-12/schema",
    }
    assert lookup["annotations"] == {
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    }
    assert lookup["_meta"] == {
        "com.samsarix/version": "1",
        "com.samsarix/tags": ["inventory", "read"],
        "com.samsarix/async": False,
    }

    reservation = tools["reserve"]
    assert reservation["outputSchema"]["properties"]["result"] == {"type": "string"}
    assert reservation["outputSchema"]["required"] == ["result"]


@pytest.mark.asyncio
async def test_mcp_tool_calls_return_structured_results_and_safe_errors() -> None:
    runtime = mcp_runtime()
    server = MCPServer(runtime)
    try:
        await initialize(server)
        found = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "inventory", "arguments": {"sku": "A-1"}},
            }
        )
        scalar = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "reserve", "arguments": {"sku": "A-1", "quantity": 2}},
            }
        )
        invalid = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "reserve", "arguments": {"sku": "A-1", "quantity": True}},
            }
        )
        failed = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "explode", "arguments": {"secret": "token"}},
            }
        )
    finally:
        await runtime.aclose()

    assert found is not None and found["result"]["isError"] is False
    assert found["result"]["structuredContent"] == {"sku": "A-1", "available": 7}
    assert json.loads(found["result"]["content"][0]["text"]) == {
        "sku": "A-1",
        "available": 7,
    }
    assert scalar is not None
    assert scalar["result"]["structuredContent"] == {"result": "reserved:A-1:2"}
    assert invalid is not None and invalid["result"]["isError"] is True
    assert json.loads(invalid["result"]["content"][0]["text"])["error"]["code"] == (
        "invalid_arguments"
    )
    assert failed is not None and failed["result"]["isError"] is True
    assert "token" not in json.dumps(failed)


@pytest.mark.asyncio
async def test_mcp_cancel_notification_stops_active_call_without_a_response() -> None:
    started = asyncio.Event()
    stopped = asyncio.Event()
    release = asyncio.Event()

    @samsarix_tool(timeout=5.0)
    async def wait_for_release() -> str:
        """Wait until the test permits completion."""

        started.set()
        try:
            await release.wait()
        finally:
            stopped.set()
        return "released"

    runtime = ToolRuntime()
    runtime.register(wait_for_release)
    server = MCPServer(runtime)
    try:
        await initialize(server)
        call = asyncio.create_task(
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "slow-call",
                    "method": "tools/call",
                    "params": {"name": "wait_for_release", "arguments": {}},
                }
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)

        assert (
            await server.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": "unknown", "reason": "ignored"},
                }
            )
            is None
        )
        await asyncio.sleep(0)
        assert not call.done()

        duplicate = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": "slow-call",
                "method": "tools/call",
                "params": {"name": "wait_for_release", "arguments": {}},
            }
        )
        assert duplicate is not None
        assert duplicate["error"] == {
            "code": -32600,
            "message": "Request id is already active",
        }

        assert (
            await server.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {
                        "requestId": "slow-call",
                        "reason": "client stopped waiting",
                    },
                }
            )
            is None
        )
        assert await asyncio.wait_for(call, timeout=1.0) is None
        await asyncio.wait_for(stopped.wait(), timeout=1.0)
        metrics = runtime.metrics()
        assert metrics.cancelled == 1
        assert metrics.in_flight == 0
    finally:
        release.set()
        await runtime.aclose()


@pytest.mark.asyncio
async def test_host_task_cancellation_still_propagates() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @samsarix_tool(timeout=5.0)
    async def wait_for_host() -> str:
        """Wait until the host permits completion."""

        started.set()
        await release.wait()
        return "released"

    runtime = ToolRuntime()
    runtime.register(wait_for_host)
    server = MCPServer(runtime)
    try:
        await initialize(server)
        call = asyncio.create_task(
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "host-call",
                    "method": "tools/call",
                    "params": {"name": "wait_for_host", "arguments": {}},
                }
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1.0)
        call.cancel()
        with pytest.raises(asyncio.CancelledError):
            await call
    finally:
        release.set()
        await runtime.aclose()


@pytest.mark.asyncio
async def test_mcp_protocol_errors_are_json_rpc_errors() -> None:
    runtime = mcp_runtime()
    server = MCPServer(runtime)
    try:
        invalid = await server.handle({"jsonrpc": "1.0", "id": 1, "method": "ping"})
        invalid_id = await server.handle({"jsonrpc": "2.0", "id": True, "method": "ping"})
        invalid_method = await server.handle({"jsonrpc": "2.0", "id": 7, "method": 7})
        invalid_params = await server.handle(
            {"jsonrpc": "2.0", "id": 8, "method": "ping", "params": []}
        )
        assert await server.handle({"jsonrpc": "2.0", "method": 7}) is None
        assert (
            await server.handle(
                {"jsonrpc": "2.0", "method": "notifications/progress", "params": []}
            )
            is None
        )
        assert (
            await server.handle(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/cancelled",
                    "params": {"requestId": True},
                }
            )
            is None
        )
        await initialize(server)
        unknown = await server.handle(
            {"jsonrpc": "2.0", "id": 2, "method": "unknown", "params": {}}
        )
        bad_cursor = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/list",
                "params": {"cursor": "next"},
            }
        )
        bad_name = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {"name": "", "arguments": {}},
            }
        )
        bad_arguments = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {"name": "inventory", "arguments": []},
            }
        )
        bad_progress_meta = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "inventory", "arguments": {}, "_meta": []},
            }
        )
        null_progress_meta = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": "null-meta",
                "method": "tools/call",
                "params": {"name": "inventory", "arguments": {}, "_meta": None},
            }
        )
        bad_progress_token = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": 7,
                "method": "tools/call",
                "params": {
                    "name": "inventory",
                    "arguments": {},
                    "_meta": {"progressToken": True},
                },
            }
        )
    finally:
        await runtime.aclose()

    assert invalid is not None and invalid["error"]["code"] == -32600
    assert invalid_id is not None and invalid_id["error"]["code"] == -32600
    assert invalid_method is not None and invalid_method["error"]["code"] == -32600
    assert invalid_params is not None and invalid_params["error"]["code"] == -32602
    assert unknown is not None and unknown["error"]["code"] == -32601
    assert bad_cursor is not None and bad_cursor["error"]["code"] == -32602
    assert bad_name is not None and bad_name["error"]["code"] == -32602
    assert bad_arguments is not None and bad_arguments["error"]["code"] == -32602
    assert bad_progress_meta is not None and bad_progress_meta["error"]["code"] == -32602
    assert null_progress_meta is not None and null_progress_meta["error"]["code"] == -32602
    assert bad_progress_token is not None and bad_progress_token["error"]["code"] == -32602


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "params",
    [
        {"capabilities": {}, "clientInfo": {}},
        {"protocolVersion": MCP_PROTOCOL_VERSION, "clientInfo": {}},
        {"protocolVersion": MCP_PROTOCOL_VERSION, "capabilities": {}},
    ],
)
async def test_mcp_initialize_requires_complete_client_metadata(params: dict) -> None:
    runtime = ToolRuntime()
    try:
        response = await MCPServer(runtime).handle(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": params}
        )
    finally:
        await runtime.aclose()

    assert response is not None and response["error"]["code"] == -32602


@pytest.mark.asyncio
async def test_stdio_transport_is_bounded_and_emits_only_protocol_messages() -> None:
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "stdio-test", "version": "1"},
        },
    }
    payload = (
        json.dumps(initialize_request)
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"})
        + "\n"
        + json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        + "\n"
    ).encode()
    reader = io.BytesIO(payload)
    writer = io.StringIO()
    runtime = mcp_runtime()

    await serve_stdio(MCPServer(runtime), input_stream=reader, output_stream=writer)

    responses = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[1]["result"]["tools"][0]["name"] == "explode"
    assert runtime.metrics().in_flight == 0
    assert (await runtime.invoke("inventory", {"sku": "A-1"})).error.code == "runtime_closed"


@pytest.mark.asyncio
async def test_stdio_emits_requested_progress_before_the_tool_response() -> None:
    @samsarix_tool
    async def index_records() -> str:
        """Report deterministic progress while indexing records."""

        assert await report_progress(1, total=2, message="loaded")
        assert await report_progress(2, total=2, message="indexed")
        return "done"

    runtime = ToolRuntime()
    runtime.register(index_records)
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "progress-test", "version": "1"},
        },
    }
    messages = [
        initialize_request,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": "index-call",
            "method": "tools/call",
            "params": {
                "name": "index_records",
                "arguments": {},
                "_meta": {"progressToken": "progress-42"},
            },
        },
    ]
    reader = io.BytesIO(("\n".join(json.dumps(item) for item in messages) + "\n").encode())
    writer = io.StringIO()

    await serve_stdio(MCPServer(runtime), input_stream=reader, output_stream=writer)

    output = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [message.get("id") for message in output] == [1, None, None, "index-call"]
    assert [message["params"] for message in output[1:3]] == [
        {
            "progressToken": "progress-42",
            "progress": 1.0,
            "total": 2.0,
            "message": "loaded",
        },
        {
            "progressToken": "progress-42",
            "progress": 2.0,
            "total": 2.0,
            "message": "indexed",
        },
    ]
    assert output[3]["result"]["structuredContent"] == {"result": "done"}


@pytest.mark.asyncio
async def test_mcp_rejects_duplicate_active_progress_tokens() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    @samsarix_tool(timeout=5)
    async def wait_with_progress() -> str:
        """Remain active while the duplicate request is checked."""

        started.set()
        await release.wait()
        return "done"

    async def discard_notification(message: dict) -> None:
        return None

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(wait_with_progress)
    server = MCPServer(runtime)
    try:
        await initialize(server)
        first = asyncio.create_task(
            server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "first",
                    "method": "tools/call",
                    "params": {
                        "name": "wait_with_progress",
                        "arguments": {},
                        "_meta": {"progressToken": 7},
                    },
                },
                notification_sender=discard_notification,
            )
        )
        await asyncio.wait_for(started.wait(), timeout=1)
        duplicate = await server.handle(
            {
                "jsonrpc": "2.0",
                "id": "second",
                "method": "tools/call",
                "params": {
                    "name": "wait_with_progress",
                    "arguments": {},
                    "_meta": {"progressToken": 7},
                },
            },
            notification_sender=discard_notification,
        )
        await server.handle(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": "first"},
            }
        )
        assert await asyncio.wait_for(first, timeout=1) is None
    finally:
        release.set()
        await runtime.aclose()

    assert duplicate is not None
    assert duplicate["error"] == {
        "code": -32602,
        "message": "progressToken is already active",
    }


@pytest.mark.asyncio
async def test_mcp_progress_sender_failure_propagates_to_the_transport() -> None:
    @samsarix_tool
    async def reporting_tool() -> str:
        """Send one update through a broken custom transport."""

        await report_progress(1)
        return "unexpected"

    async def broken_sender(message: dict) -> None:
        raise OSError("notification writer failed")

    runtime = ToolRuntime()
    runtime.register(reporting_tool)
    server = MCPServer(runtime)
    try:
        await initialize(server)
        with pytest.raises(ProgressHandlerError) as raised:
            await server.handle(
                {
                    "jsonrpc": "2.0",
                    "id": "reporting",
                    "method": "tools/call",
                    "params": {
                        "name": "reporting_tool",
                        "arguments": {},
                        "_meta": {"progressToken": "broken"},
                    },
                },
                notification_sender=broken_sender,
            )
    finally:
        await runtime.aclose()

    assert isinstance(raised.value.__cause__, OSError)
    assert str(raised.value.__cause__) == "notification writer failed"


@pytest.mark.asyncio
async def test_stdio_drops_an_oversized_progress_notification_without_spurious_error() -> None:
    @samsarix_tool
    async def noisy_progress() -> str:
        """Emit a progress message larger than the transport limit."""

        assert await report_progress(1, message="x" * 600)
        return "done"

    runtime = ToolRuntime(max_progress_message_bytes=1_024)
    runtime.register(noisy_progress)
    server = MCPServer(runtime)
    await initialize(server)
    request = {
        "jsonrpc": "2.0",
        "id": "noisy",
        "method": "tools/call",
        "params": {
            "name": "noisy_progress",
            "arguments": {},
            "_meta": {"progressToken": "noise"},
        },
    }
    writer = io.StringIO()
    await serve_stdio(
        server,
        input_stream=io.BytesIO((json.dumps(request) + "\n").encode()),
        output_stream=writer,
        max_message_bytes=512,
        close_runtime=False,
    )

    output = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert len(output) == 1
    assert output[0]["id"] == "noisy"
    assert output[0]["result"]["structuredContent"] == {"result": "done"}
    await runtime.aclose()


@pytest.mark.asyncio
async def test_stdio_cancels_active_calls_and_rejects_excess_admission() -> None:
    started = Event()
    stopped = asyncio.Event()
    never_release = asyncio.Event()

    @samsarix_tool(timeout=5.0)
    async def slow_operation() -> str:
        """Remain active until the client cancels the request."""

        started.set()
        try:
            await never_release.wait()
        finally:
            stopped.set()
        return "unexpected"

    runtime = ToolRuntime(max_concurrency=1)
    runtime.register(slow_operation)
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "cancel-test", "version": "1"},
        },
    }
    messages = [
        initialize_request,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": "active",
            "method": "tools/call",
            "params": {"name": "slow_operation", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": True,
            "method": "tools/call",
            "params": {"name": "slow_operation", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": "excess",
            "method": "tools/call",
            "params": {"name": "slow_operation", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": "active"},
        },
        {"jsonrpc": "2.0", "id": "catalog", "method": "tools/list"},
    ]

    class GatedReader(io.BytesIO):
        def __init__(self, value: bytes) -> None:
            super().__init__(value)
            self.gated = False

        def readline(self, size: int = -1) -> bytes:
            line = super().readline(size)
            message = json.loads(line) if line else {}
            if message.get("id") == "excess":
                self.gated = True
                assert started.wait(timeout=1.0)
            return line

    payload = ("\n".join(json.dumps(message) for message in messages) + "\n").encode()
    writer = io.StringIO()
    reader = GatedReader(payload)
    await serve_stdio(
        MCPServer(runtime),
        input_stream=reader,
        output_stream=writer,
        max_in_flight_requests=1,
        close_runtime=False,
    )

    responses = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert reader.gated
    assert [response["id"] for response in responses] == [1, None, "excess", "catalog"]
    assert responses[1]["error"]["code"] == -32600
    assert responses[2]["error"] == {
        "code": -32000,
        "message": "Too many in-flight MCP requests",
    }
    assert responses[3]["result"]["tools"][0]["name"] == "slow_operation"
    await asyncio.wait_for(stopped.wait(), timeout=1.0)
    assert runtime.metrics().cancelled == 1
    await runtime.aclose()


@pytest.mark.asyncio
async def test_stdio_drains_an_admitted_call_at_normal_eof() -> None:
    @samsarix_tool
    async def delayed() -> str:
        """Return after yielding once."""

        await asyncio.sleep(0.01)
        return "done"

    runtime = ToolRuntime()
    runtime.register(delayed)
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": "drain-test", "version": "1"},
        },
    }
    messages = [
        initialize_request,
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "delayed", "arguments": {}},
        },
    ]
    reader = io.BytesIO(("\n".join(json.dumps(message) for message in messages) + "\n").encode())
    writer = io.StringIO()

    await serve_stdio(MCPServer(runtime), input_stream=reader, output_stream=writer)

    responses = [json.loads(line) for line in writer.getvalue().splitlines()]
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[1]["result"]["structuredContent"] == {"result": "done"}


@pytest.mark.asyncio
async def test_stdio_cancels_and_joins_siblings_after_background_write_failure() -> None:
    started = Event()
    stopped = asyncio.Event()
    never_release = asyncio.Event()

    @samsarix_tool(timeout=5.0)
    async def slow_operation() -> str:
        """Remain active while a sibling transport task fails."""

        started.set()
        try:
            await never_release.wait()
        finally:
            stopped.set()
        return "unexpected"

    @samsarix_tool
    async def fast_operation() -> str:
        """Complete so its response exercises a broken writer."""

        return "done"

    runtime = ToolRuntime(max_concurrency=2)
    runtime.register(slow_operation)
    runtime.register(fast_operation)
    server = MCPServer(runtime)
    await initialize(server)
    messages = [
        {
            "jsonrpc": "2.0",
            "id": "slow",
            "method": "tools/call",
            "params": {"name": "slow_operation", "arguments": {}},
        },
        {
            "jsonrpc": "2.0",
            "id": "fast",
            "method": "tools/call",
            "params": {"name": "fast_operation", "arguments": {}},
        },
    ]

    class GatedReader(io.BytesIO):
        gated = False

        def readline(self, size: int = -1) -> bytes:
            line = super().readline(size)
            message = json.loads(line) if line else {}
            if message.get("id") == "fast":
                self.gated = True
                assert started.wait(timeout=1.0)
            return line

    class FailingWriter(io.StringIO):
        def write(self, value: str) -> int:
            raise OSError("writer failed")

    payload = ("\n".join(json.dumps(message) for message in messages) + "\n").encode()
    reader = GatedReader(payload)
    try:
        with pytest.raises(OSError, match="writer failed"):
            await serve_stdio(
                server,
                input_stream=reader,
                output_stream=FailingWriter(),
                close_runtime=False,
            )
        assert reader.gated
        await asyncio.wait_for(stopped.wait(), timeout=1.0)
        assert runtime.metrics().cancelled == 1
        assert runtime.metrics().in_flight == 0
    finally:
        await runtime.aclose()


@pytest.mark.asyncio
async def test_stdio_transport_handles_parse_errors_and_oversized_lines() -> None:
    runtime = mcp_runtime()
    parse_writer = io.StringIO()
    await serve_stdio(
        MCPServer(runtime),
        input_stream=io.BytesIO(b"{bad json\n[]\n"),
        output_stream=parse_writer,
        close_runtime=False,
    )
    parsed = [json.loads(line) for line in parse_writer.getvalue().splitlines()]
    assert [item["error"]["code"] for item in parsed] == [-32700, -32600]

    oversized_writer = io.StringIO()
    await serve_stdio(
        MCPServer(runtime),
        input_stream=io.BytesIO(b"x" * 512 + b"\n"),
        output_stream=oversized_writer,
        max_message_bytes=256,
        close_runtime=False,
    )
    oversized = json.loads(oversized_writer.getvalue())
    assert oversized["error"]["message"] == "MCP message exceeds limit"

    catalog_server = MCPServer(runtime)
    await initialize(catalog_server)
    response_writer = io.StringIO()
    catalog_request = json.dumps(
        {"jsonrpc": "2.0", "id": "catalog-99", "method": "tools/list", "params": {}}
    ).encode()
    await serve_stdio(
        catalog_server,
        input_stream=io.BytesIO(catalog_request + b"\n"),
        output_stream=response_writer,
        max_message_bytes=256,
        close_runtime=False,
    )
    limited = json.loads(response_writer.getvalue())
    assert limited == {
        "error": {"code": -32603, "message": "MCP response exceeds limit"},
        "id": "catalog-99",
        "jsonrpc": "2.0",
    }
    await runtime.aclose()


def test_mcp_metadata_validation_is_conservative() -> None:
    with pytest.raises(ValueError, match="Read-only"):

        @samsarix_tool(read_only=True, destructive=True)
        def contradictory() -> str:
            """Declare contradictory behavior."""

            return "no"

    with pytest.raises(ValueError, match="read_only"):

        @samsarix_tool(read_only="yes")  # type: ignore[arg-type]
        def invalid_boolean() -> str:
            """Declare invalid behavior."""

            return "no"

    with pytest.raises(ValueError, match="title"):

        @samsarix_tool(title=" ")
        def invalid_title() -> str:
            """Declare invalid behavior."""

            return "no"


def test_mcp_server_metadata_and_transport_limits_are_validated() -> None:
    runtime = ToolRuntime()
    try:
        with pytest.raises(ValueError, match="name"):
            MCPServer(runtime, name=" ")
        with pytest.raises(ValueError, match="instructions"):
            MCPServer(runtime, instructions=" ")
        with pytest.raises(TypeError, match="max_message_bytes"):
            asyncio.run(serve_stdio(MCPServer(runtime), max_message_bytes=True))
        with pytest.raises(ValueError, match="at least 256"):
            asyncio.run(serve_stdio(MCPServer(runtime), max_message_bytes=0))
        with pytest.raises(TypeError, match="max_in_flight_requests"):
            asyncio.run(serve_stdio(MCPServer(runtime), max_in_flight_requests=True))
        with pytest.raises(ValueError, match="max_in_flight_requests"):
            asyncio.run(serve_stdio(MCPServer(runtime), max_in_flight_requests=0))
        with pytest.raises(TypeError, match="notification_sender"):
            asyncio.run(
                MCPServer(runtime).handle({}, notification_sender=True)  # type: ignore[arg-type]
            )
    finally:
        asyncio.run(runtime.aclose())
