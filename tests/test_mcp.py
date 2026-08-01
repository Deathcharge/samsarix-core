# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import io
import json

import pytest

from samsarix_core import MCPServer, ToolRuntime, samsarix_tool, serve_stdio
from samsarix_core.mcp import MCP_PROTOCOL_VERSION


@samsarix_tool(
    title="Look up inventory",
    tags=("inventory", "read"),
    read_only=True,
    open_world=False,
)
def inventory(sku: str) -> dict[str, int | str]:
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
    assert lookup["outputSchema"]["type"] == "object"
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
async def test_stdio_transport_handles_parse_errors_and_oversized_lines() -> None:
    runtime = ToolRuntime()
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
    finally:
        asyncio.run(runtime.aclose())
