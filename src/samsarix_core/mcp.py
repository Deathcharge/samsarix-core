# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Dependency-free Model Context Protocol bridge for Samsarix tools."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, BinaryIO, TextIO, cast

from ._version import __version__
from .models import JSONValue, ToolResult, ToolSpec
from .runtime import ToolRuntime

MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (MCP_PROTOCOL_VERSION, "2025-06-18")

_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_SERVER_NOT_INITIALIZED = -32002


class MCPServer:
    """Expose a :class:`ToolRuntime` through MCP's JSON-RPC tool surface.

    The server implements initialization, ping, ``tools/list``, and ``tools/call``.
    Transport and authentication remain application concerns; :func:`serve_stdio`
    provides a bounded local stdio transport for trusted process launchers.
    """

    def __init__(
        self,
        runtime: ToolRuntime,
        *,
        name: str = "samsarix-core",
        title: str = "Samsarix Core",
        version: str = __version__,
        instructions: str | None = None,
    ) -> None:
        for field_name, value in (("name", name), ("title", title), ("version", version)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MCP server {field_name} must be a non-empty string")
        if instructions is not None and (
            not isinstance(instructions, str) or not instructions.strip()
        ):
            raise ValueError("MCP server instructions must be a non-empty string")

        self.runtime = runtime
        self.name = name.strip()
        self.title = title.strip()
        self.version = version.strip()
        self.instructions = instructions.strip() if instructions is not None else None
        self._initialize_responded = False
        self._initialized = False
        self._protocol_version: str | None = None

    async def handle(self, message: Mapping[str, Any]) -> dict[str, JSONValue] | None:
        """Handle one parsed JSON-RPC message and return a response if required."""

        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
            return self._error(None, _INVALID_REQUEST, "Invalid JSON-RPC request")

        request_id = message.get("id")
        is_notification = "id" not in message
        if not is_notification and not _valid_request_id(request_id):
            return self._error(None, _INVALID_REQUEST, "Request id must be a string or number")

        method = message.get("method")
        if not isinstance(method, str) or not method:
            if is_notification:
                return None
            return self._error(request_id, _INVALID_REQUEST, "Request method must be a string")

        params = message.get("params", {})
        if not isinstance(params, Mapping):
            if is_notification:
                return None
            return self._error(request_id, _INVALID_PARAMS, "Request params must be an object")

        if is_notification:
            if method == "notifications/initialized" and self._initialize_responded:
                self._initialized = True
            return None

        try:
            if method == "initialize":
                return self._success(request_id, self._initialize(params))
            if method == "ping":
                return self._success(request_id, {})
            if not self._initialized:
                return self._error(
                    request_id,
                    _SERVER_NOT_INITIALIZED,
                    "Server has not completed MCP initialization",
                )
            if method == "tools/list":
                return self._success(request_id, self._list_tools(params))
            if method == "tools/call":
                return self._success(request_id, await self._call_tool(params))
            return self._error(request_id, _METHOD_NOT_FOUND, f"Unknown method '{method}'")
        except _InvalidParams as exc:
            return self._error(request_id, _INVALID_PARAMS, str(exc))
        except Exception:
            return self._error(request_id, _INTERNAL_ERROR, "Internal server error")

    def _initialize(self, params: Mapping[str, Any]) -> dict[str, JSONValue]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str) or not requested:
            raise _InvalidParams("initialize requires a protocolVersion string")
        if not isinstance(params.get("capabilities"), Mapping):
            raise _InvalidParams("initialize requires client capabilities")
        if not isinstance(params.get("clientInfo"), Mapping):
            raise _InvalidParams("initialize requires clientInfo")

        negotiated = requested if requested in SUPPORTED_PROTOCOL_VERSIONS else MCP_PROTOCOL_VERSION
        self._initialize_responded = True
        self._initialized = False
        self._protocol_version = negotiated
        result: dict[str, JSONValue] = {
            "protocolVersion": negotiated,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {
                "name": self.name,
                "title": self.title,
                "version": self.version,
                "websiteUrl": "https://samsarix.com",
            },
        }
        if self.instructions is not None:
            result["instructions"] = self.instructions
        return result

    def _list_tools(self, params: Mapping[str, Any]) -> dict[str, JSONValue]:
        cursor = params.get("cursor")
        if cursor is not None:
            raise _InvalidParams("Pagination cursors are not supported by this bounded registry")
        return {"tools": [self._tool_definition(spec) for spec in self.runtime.registry.list()]}

    async def _call_tool(self, params: Mapping[str, Any]) -> dict[str, JSONValue]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _InvalidParams("tools/call requires a tool name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise _InvalidParams("tools/call arguments must be an object")

        result = await self.runtime.invoke(name, cast(dict[str, Any], arguments))
        return self._tool_result(result)

    @staticmethod
    def _tool_definition(spec: ToolSpec) -> dict[str, JSONValue]:
        output_schema, _ = _mcp_output_schema(spec.output_schema)
        definition: dict[str, JSONValue] = {
            "name": spec.name,
            "description": spec.description,
            "inputSchema": deepcopy(spec.input_schema),
            "outputSchema": output_schema,
            "annotations": {
                "readOnlyHint": spec.read_only,
                "destructiveHint": spec.destructive,
                "idempotentHint": spec.idempotent,
                "openWorldHint": spec.open_world,
            },
            "_meta": {
                "com.samsarix/version": spec.version,
                "com.samsarix/tags": list(spec.tags),
                "com.samsarix/async": spec.is_async,
            },
        }
        if spec.title is not None:
            definition["title"] = spec.title
        return definition

    def _tool_result(self, result: ToolResult) -> dict[str, JSONValue]:
        metadata: dict[str, JSONValue] = {
            "com.samsarix/invocation-id": result.invocation_id,
            "com.samsarix/status": result.status.value,
            "com.samsarix/duration-ms": result.duration_ms,
        }
        if result.success:
            spec = self.runtime.registry.get(result.tool_name)
            _, wrapped = _mcp_output_schema(spec.output_schema)
            structured: dict[str, JSONValue]
            if wrapped:
                structured = {"result": result.output}
            else:
                structured = cast(dict[str, JSONValue], deepcopy(result.output))
            return {
                "content": [{"type": "text", "text": _json_text(structured)}],
                "structuredContent": structured,
                "isError": False,
                "_meta": metadata,
            }

        error = (
            result.error.to_dict()
            if result.error is not None
            else {
                "code": "unknown_error",
                "message": "Tool invocation failed",
                "retryable": False,
            }
        )
        return {
            "content": [{"type": "text", "text": _json_text({"error": error})}],
            "isError": True,
            "_meta": metadata,
        }

    @staticmethod
    def _success(request_id: Any, result: Mapping[str, Any]) -> dict[str, JSONValue]:
        return {
            "jsonrpc": "2.0",
            "id": cast(JSONValue, request_id),
            "result": cast(JSONValue, deepcopy(dict(result))),
        }

    @staticmethod
    def _error(request_id: Any, code: int, message: str) -> dict[str, JSONValue]:
        return {
            "jsonrpc": "2.0",
            "id": cast(JSONValue, request_id),
            "error": {"code": code, "message": message},
        }


async def serve_stdio(
    server: MCPServer,
    *,
    input_stream: BinaryIO | None = None,
    output_stream: TextIO | None = None,
    max_message_bytes: int = 1_048_576,
    close_runtime: bool = True,
) -> None:
    """Serve newline-delimited MCP JSON-RPC over trusted local stdio.

    Protocol messages are the only data written to stdout. Applications should
    send diagnostics to stderr and obtain credentials from their environment.
    """

    if isinstance(max_message_bytes, bool) or not isinstance(max_message_bytes, int):
        raise TypeError("max_message_bytes must be an integer")
    if max_message_bytes < 256:
        raise ValueError("max_message_bytes must be at least 256")

    reader = input_stream if input_stream is not None else sys.stdin.buffer
    writer = output_stream
    try:
        while True:
            line = await asyncio.to_thread(reader.readline, max_message_bytes + 1)
            if not line:
                break
            response: dict[str, JSONValue] | None
            if len(line) > max_message_bytes:
                if not line.endswith(b"\n"):
                    await _discard_line(reader, max_message_bytes)
                response = MCPServer._error(None, _INVALID_REQUEST, "MCP message exceeds limit")
            else:
                response = await _handle_json_line(server, line)
            if response is not None:
                encoded = _json_text(response)
                if len(encoded.encode("utf-8")) > max_message_bytes:
                    encoded = _json_text(
                        MCPServer._error(None, _INTERNAL_ERROR, "MCP response exceeds limit")
                    )
                if writer is None:
                    sys.stdout.buffer.write((encoded + "\n").encode("utf-8"))
                    sys.stdout.buffer.flush()
                else:
                    writer.write(encoded + "\n")
                    writer.flush()
    finally:
        if close_runtime:
            await server.runtime.aclose()


async def _handle_json_line(server: MCPServer, line: bytes) -> dict[str, JSONValue] | None:
    try:
        decoded = line.decode("utf-8")
        message = json.loads(decoded)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return MCPServer._error(None, -32700, "Parse error")
    if not isinstance(message, dict):
        return MCPServer._error(None, _INVALID_REQUEST, "Invalid JSON-RPC request")
    return await server.handle(message)


async def _discard_line(reader: BinaryIO, chunk_size: int) -> None:
    """Discard the remainder of an oversized input without buffering it."""

    while True:
        chunk = await asyncio.to_thread(reader.readline, chunk_size + 1)
        if not chunk or chunk.endswith(b"\n") or len(chunk) <= chunk_size:
            return


def _mcp_output_schema(schema: Mapping[str, Any]) -> tuple[dict[str, JSONValue], bool]:
    output = cast(dict[str, JSONValue], deepcopy(dict(schema)))
    if output.get("type") == "object":
        return output, False

    nested = deepcopy(output)
    nested.pop("$schema", None)
    return (
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {"result": nested},
            "required": ["result"],
            "additionalProperties": False,
        },
        True,
    )


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _valid_request_id(value: Any) -> bool:
    return isinstance(value, (str, int, float)) and not isinstance(value, bool)


class _InvalidParams(ValueError):
    """Private control-flow exception for safe JSON-RPC parameter errors."""
