# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Malformed protocol metadata must not poison a stdio session."""

from __future__ import annotations

import asyncio
import io
import json

import pytest

from samsarix_core import MCPServer, ToolRuntime, report_progress, samsarix_tool, serve_stdio
from samsarix_core.mcp import MCP_PROTOCOL_VERSION, _write_response


async def initialize(server: MCPServer) -> None:
    response = await server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {},
            },
        }
    )
    assert response is not None and "result" in response
    await server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})


async def framed_messages(messages: list[dict], *, max_bytes: int = 1_048_576) -> list[dict]:
    payload = b"".join((json.dumps(item) + "\n").encode() for item in messages)
    writer = io.StringIO()
    await serve_stdio(
        MCPServer(ToolRuntime()),
        input_stream=io.BytesIO(payload),
        output_stream=writer,
        max_message_bytes=max_bytes,
    )
    frames = writer.getvalue().encode("utf-8").splitlines(keepends=True)
    assert all(len(frame) <= max_bytes for frame in frames)
    return [json.loads(frame) for frame in frames]


@pytest.mark.asyncio
@pytest.mark.parametrize("method", [[], {}, ["tools/call"], {"name": "tasks/result"}])
async def test_invalid_method_is_rejected_and_following_ping_survives(method) -> None:
    responses = await framed_messages(
        [
            {"jsonrpc": "2.0", "id": "bad", "method": method},
            {"jsonrpc": "2.0", "id": "good", "method": "ping"},
        ]
    )
    assert responses[0]["error"]["code"] == -32600
    assert responses[1] == {"jsonrpc": "2.0", "id": "good", "result": {}}


@pytest.mark.asyncio
@pytest.mark.parametrize("identifier", ["\ud800", "\udfff", "x\ud800y", "\U0001f680-\u6771\u4eac"])
async def test_protocol_ids_round_trip_through_safe_utf8_frames(identifier: str) -> None:
    responses = await framed_messages(
        [
            {"jsonrpc": "2.0", "id": identifier, "method": "ping"},
            {"jsonrpc": "2.0", "id": "good", "method": "ping"},
        ]
    )
    assert responses[0] == {"jsonrpc": "2.0", "id": identifier, "result": {}}
    assert responses[1]["id"] == "good"


@pytest.mark.asyncio
async def test_unknown_surrogate_method_error_is_encodable() -> None:
    runtime = ToolRuntime()
    server = MCPServer(runtime)
    await initialize(server)
    writer = io.StringIO()
    await serve_stdio(
        server,
        input_stream=io.BytesIO(b'{"jsonrpc":"2.0","id":2,"method":"bad\\ud800"}\n'),
        output_stream=writer,
    )
    response = json.loads(writer.getvalue().encode("utf-8"))
    assert response["error"]["code"] == -32601


@pytest.mark.asyncio
async def test_surrogate_progress_token_does_not_fail_tool_or_transport() -> None:
    @samsarix_tool
    async def progress() -> str:
        """Emit one progress notification."""
        await report_progress(1, total=1)
        return "done"

    runtime = ToolRuntime()
    runtime.register(progress)
    server = MCPServer(runtime)
    await initialize(server)
    request = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "progress", "_meta": {"progressToken": "\ud800"}},
    }
    writer = io.StringIO()
    await serve_stdio(
        server, input_stream=io.BytesIO((json.dumps(request) + "\n").encode()), output_stream=writer
    )
    messages = [json.loads(line) for line in writer.getvalue().encode("utf-8").splitlines()]
    assert messages[0]["params"]["progressToken"] == "\ud800"
    assert messages[-1]["result"]["isError"] is False


@pytest.mark.asyncio
async def test_large_id_fallback_and_delimiter_fit_message_cap() -> None:
    messages = await framed_messages(
        [
            {"jsonrpc": "2.0", "id": "x" * 175, "method": []},
            {"jsonrpc": "2.0", "id": "good", "method": "ping"},
        ],
        max_bytes=256,
    )
    assert messages[0]["id"] is None
    assert messages[0]["error"]["code"] == -32603
    assert messages[1]["result"] == {}


@pytest.mark.asyncio
async def test_response_cap_counts_newline_and_oversized_notifications_are_dropped(capsys) -> None:
    response = {"jsonrpc": "2.0", "id": "small", "result": "x" * 300}
    exact_json_size = len(json.dumps(response, separators=(",", ":"), sort_keys=True).encode())
    writer = io.StringIO()
    await _write_response(
        response, writer=writer, max_message_bytes=exact_json_size, lock=asyncio.Lock()
    )
    assert len(writer.getvalue().encode()) <= exact_json_size
    assert json.loads(writer.getvalue())["error"]["code"] == -32603

    writer = io.StringIO()
    await _write_response(
        {"jsonrpc": "2.0", "method": "notification", "params": "x" * 300},
        writer=writer,
        max_message_bytes=256,
        lock=asyncio.Lock(),
    )
    assert writer.getvalue() == ""
    assert "dropped an oversized MCP notification" in capsys.readouterr().err
