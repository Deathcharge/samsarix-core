# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Dependency-free Model Context Protocol bridge for Samsarix tools."""

from __future__ import annotations

import asyncio
import json
import math
import sys
from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from typing import Any, BinaryIO, TextIO, cast

from ._version import __version__
from .errors import ProgressHandlerError, ToolNotFoundError
from .models import JSONValue, ToolResult, ToolSpec
from .progress import ProgressHandler, ToolProgress
from .runtime import ToolRuntime

MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = (MCP_PROTOCOL_VERSION, "2025-06-18")

_INVALID_REQUEST = -32600
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_SERVER_NOT_INITIALIZED = -32002
_SERVER_BUSY = -32000

NotificationSender = Callable[[dict[str, JSONValue]], Awaitable[None]]

_LOG_LEVELS = (
    "debug",
    "info",
    "notice",
    "warning",
    "error",
    "critical",
    "alert",
    "emergency",
)
_LOG_LEVEL_ORDER = {level: position for position, level in enumerate(_LOG_LEVELS)}


class MCPServer:
    """Expose a :class:`ToolRuntime` through MCP's JSON-RPC tool surface.

    The server implements initialization, ping, ``tools/list``, ``tools/call``,
    progress reporting, optional content-free operational logging, and
    cancellation of active calls. Transport and authentication remain application
    concerns; :func:`serve_stdio` provides a bounded local stdio transport for
    trusted process launchers.
    """

    def __init__(
        self,
        runtime: ToolRuntime,
        *,
        name: str = "samsarix-core",
        title: str = "Samsarix Core",
        version: str = __version__,
        instructions: str | None = None,
        enable_logging: bool = False,
        default_log_level: str = "warning",
    ) -> None:
        for field_name, value in (("name", name), ("title", title), ("version", version)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"MCP server {field_name} must be a non-empty string")
        if instructions is not None and (
            not isinstance(instructions, str) or not instructions.strip()
        ):
            raise ValueError("MCP server instructions must be a non-empty string")
        if not isinstance(enable_logging, bool):
            raise TypeError("enable_logging must be a boolean")
        if not isinstance(default_log_level, str):
            raise TypeError("default_log_level must be a string")
        if default_log_level not in _LOG_LEVEL_ORDER:
            raise ValueError(f"default_log_level must be one of {', '.join(_LOG_LEVELS)}")

        self.runtime = runtime
        self.name = name.strip()
        self.title = title.strip()
        self.version = version.strip()
        self.instructions = instructions.strip() if instructions is not None else None
        self._logging_enabled = enable_logging
        self._default_log_level = default_log_level
        self._minimum_log_level = default_log_level
        self._initialize_responded = False
        self._initialized = False
        self._protocol_version: str | None = None
        self._in_flight_requests: dict[str | int | float, asyncio.Task[Any]] = {}
        self._client_cancelled_tasks: set[asyncio.Task[Any]] = set()
        self._active_progress_tokens: set[str | int | float] = set()

    async def handle(
        self,
        message: Mapping[str, Any],
        *,
        notification_sender: NotificationSender | None = None,
    ) -> dict[str, JSONValue] | None:
        """Handle one parsed JSON-RPC message and return a response if required."""

        if notification_sender is not None and not callable(notification_sender):
            raise TypeError("notification_sender must be callable or None")

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
            elif method == "notifications/cancelled":
                self._cancel_request(params)
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
            if method == "logging/setLevel" and self._logging_enabled:
                return self._success(request_id, self._set_log_level(params))
            if method == "tools/list":
                return self._success(request_id, self._list_tools(params))
            if method == "tools/call":
                active = asyncio.current_task()
                if active is None:
                    return self._error(request_id, _INTERNAL_ERROR, "Internal server error")
                request_key = cast(str | int | float, request_id)
                if request_key in self._in_flight_requests:
                    return self._error(
                        request_id,
                        _INVALID_REQUEST,
                        "Request id is already active",
                    )
                self._in_flight_requests[request_key] = active
                try:
                    return self._success(
                        request_id,
                        await self._call_tool(
                            params,
                            notification_sender=notification_sender,
                        ),
                    )
                except asyncio.CancelledError:
                    if active in self._client_cancelled_tasks:
                        return None
                    raise
                finally:
                    self._client_cancelled_tasks.discard(active)
                    if self._in_flight_requests.get(request_key) is active:
                        del self._in_flight_requests[request_key]
            return self._error(request_id, _METHOD_NOT_FOUND, f"Unknown method '{method}'")
        except _InvalidParams as exc:
            return self._error(request_id, _INVALID_PARAMS, str(exc))
        except ProgressHandlerError:
            raise
        except Exception:
            return self._error(request_id, _INTERNAL_ERROR, "Internal server error")

    def _cancel_request(self, params: Mapping[str, Any]) -> None:
        """Cancel one active call named by a valid client request id."""

        request_id = params.get("requestId")
        if not _valid_request_id(request_id):
            return
        active = self._in_flight_requests.get(cast(str | int | float, request_id))
        if active is not None:
            self._client_cancelled_tasks.add(active)
            active.cancel()

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
        self._minimum_log_level = self._default_log_level
        capabilities: dict[str, JSONValue] = {"tools": {"listChanged": False}}
        if self._logging_enabled:
            capabilities["logging"] = {}
        result: dict[str, JSONValue] = {
            "protocolVersion": negotiated,
            "capabilities": capabilities,
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

    def _set_log_level(self, params: Mapping[str, Any]) -> dict[str, JSONValue]:
        level = params.get("level")
        if not isinstance(level, str) or level not in _LOG_LEVEL_ORDER:
            raise _InvalidParams(f"logging level must be one of {', '.join(_LOG_LEVELS)}")
        self._minimum_log_level = level
        return {}

    def _list_tools(self, params: Mapping[str, Any]) -> dict[str, JSONValue]:
        cursor = params.get("cursor")
        if cursor is not None:
            raise _InvalidParams("Pagination cursors are not supported by this bounded registry")
        return {"tools": [self._tool_definition(spec) for spec in self.runtime.registry.list()]}

    async def _call_tool(
        self,
        params: Mapping[str, Any],
        *,
        notification_sender: NotificationSender | None,
    ) -> dict[str, JSONValue]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise _InvalidParams("tools/call requires a tool name")
        arguments = params.get("arguments", {})
        if not isinstance(arguments, dict):
            raise _InvalidParams("tools/call arguments must be an object")

        progress_token = _request_progress_token(params)
        progress_handler = self._progress_handler(progress_token, notification_sender)
        active_progress_token = progress_token if progress_handler is not None else None
        if (
            active_progress_token is not None
            and active_progress_token in self._active_progress_tokens
        ):
            raise _InvalidParams("progressToken is already active")
        if active_progress_token is not None:
            self._active_progress_tokens.add(active_progress_token)
        try:
            result = await self.runtime.invoke(
                name,
                cast(dict[str, Any], arguments),
                progress_handler=progress_handler,
            )
            await self._send_operational_log(result, notification_sender)
            return self._tool_result(result)
        finally:
            if active_progress_token is not None:
                self._active_progress_tokens.discard(active_progress_token)

    async def _send_operational_log(
        self,
        result: ToolResult,
        notification_sender: NotificationSender | None,
    ) -> bool:
        """Best-effort one content-free terminal event for an invocation."""

        if not self._logging_enabled or notification_sender is None:
            return False
        level = "info" if result.success else "error"
        if _LOG_LEVEL_ORDER[level] < _LOG_LEVEL_ORDER[self._minimum_log_level]:
            return False
        try:
            registered_name = self.runtime.registry.get(result.tool_name).name
        except ToolNotFoundError:
            return False
        try:
            await notification_sender(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/message",
                    "params": {
                        "level": level,
                        "logger": self.name,
                        "data": {
                            "event": "tool_invocation",
                            "tool": registered_name,
                            "invocationId": result.invocation_id,
                            "status": result.status.value,
                            "durationMs": result.duration_ms,
                        },
                    },
                }
            )
        except Exception:
            # Operational diagnostics must not replace an already-computed tool result.
            return False
        return True

    @staticmethod
    def _progress_handler(
        progress_token: str | int | float | None,
        notification_sender: NotificationSender | None,
    ) -> ProgressHandler | None:
        if progress_token is None or notification_sender is None:
            return None

        async def send(update: ToolProgress) -> None:
            params: dict[str, JSONValue] = {
                "progressToken": progress_token,
                "progress": update.progress,
            }
            if update.total is not None:
                params["total"] = update.total
            if update.message is not None:
                params["message"] = update.message
            await notification_sender(
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/progress",
                    "params": params,
                }
            )

        return send

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
    max_in_flight_requests: int = 64,
    close_runtime: bool = True,
) -> None:
    """Serve newline-delimited MCP JSON-RPC over trusted local stdio.

    Tool calls run concurrently so control notifications remain responsive, with
    admission bounded by ``max_in_flight_requests``. Protocol messages are the
    only data written to stdout. Applications should send diagnostics to stderr
    and obtain credentials from their environment.
    """

    if isinstance(max_message_bytes, bool) or not isinstance(max_message_bytes, int):
        raise TypeError("max_message_bytes must be an integer")
    if max_message_bytes < 256:
        raise ValueError("max_message_bytes must be at least 256")
    if isinstance(max_in_flight_requests, bool) or not isinstance(max_in_flight_requests, int):
        raise TypeError("max_in_flight_requests must be an integer")
    if max_in_flight_requests <= 0:
        raise ValueError("max_in_flight_requests must be positive")

    reader = input_stream if input_stream is not None else sys.stdin.buffer
    writer = output_stream
    write_lock = asyncio.Lock()
    in_flight: set[asyncio.Task[None]] = set()
    task_errors: list[BaseException] = []

    def request_finished(task: asyncio.Task[None]) -> None:
        """Remove one transport task and retain any unhandled failure."""

        in_flight.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            task_errors.append(error)
            for sibling in tuple(in_flight):
                sibling.cancel()

    async def cancel_in_flight() -> None:
        """Cancel and join every transport task admitted at this instant."""

        pending = tuple(in_flight)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    try:
        while True:
            if task_errors:
                raise task_errors.pop(0)
            line = await asyncio.to_thread(reader.readline, max_message_bytes + 1)
            if not line:
                break
            if len(line) > max_message_bytes:
                if not line.endswith(b"\n"):
                    await _discard_line(reader, max_message_bytes)
                await _write_response(
                    MCPServer._error(None, _INVALID_REQUEST, "MCP message exceeds limit"),
                    writer=writer,
                    max_message_bytes=max_message_bytes,
                    lock=write_lock,
                )
                continue

            message, parse_error = _parse_json_line(line)
            if parse_error is not None:
                await _write_response(
                    parse_error,
                    writer=writer,
                    max_message_bytes=max_message_bytes,
                    lock=write_lock,
                )
                continue
            if message is None:
                await _write_response(
                    MCPServer._error(None, _INTERNAL_ERROR, "Internal server error"),
                    writer=writer,
                    max_message_bytes=max_message_bytes,
                    lock=write_lock,
                )
                continue

            if _is_tool_call_request(message):
                if len(in_flight) >= max_in_flight_requests:
                    await _write_response(
                        MCPServer._error(
                            message["id"],
                            _SERVER_BUSY,
                            "Too many in-flight MCP requests",
                        ),
                        writer=writer,
                        max_message_bytes=max_message_bytes,
                        lock=write_lock,
                    )
                    continue
                task = asyncio.create_task(
                    _handle_and_write(
                        server,
                        message,
                        writer=writer,
                        max_message_bytes=max_message_bytes,
                        lock=write_lock,
                    )
                )
                in_flight.add(task)
                task.add_done_callback(request_finished)
                await asyncio.sleep(0)
                continue

            await _handle_and_write(
                server,
                message,
                writer=writer,
                max_message_bytes=max_message_bytes,
                lock=write_lock,
            )

        if in_flight:
            outcomes = await asyncio.gather(*tuple(in_flight), return_exceptions=True)
            if task_errors:
                raise task_errors.pop(0)
            for outcome in outcomes:
                if isinstance(outcome, BaseException):
                    raise outcome
        if task_errors:
            raise task_errors.pop(0)
    except BaseException:
        await cancel_in_flight()
        raise
    finally:
        if close_runtime:
            await server.runtime.aclose()


def _parse_json_line(
    line: bytes,
) -> tuple[dict[str, Any] | None, dict[str, JSONValue] | None]:
    """Parse one bounded input line into either a message or safe error."""

    try:
        decoded = line.decode("utf-8")
        message = json.loads(decoded)
    except (UnicodeDecodeError, ValueError, RecursionError):
        return None, MCPServer._error(None, -32700, "Parse error")
    if not isinstance(message, dict):
        return None, MCPServer._error(None, _INVALID_REQUEST, "Invalid JSON-RPC request")
    return cast(dict[str, Any], message), None


def _is_tool_call_request(message: Mapping[str, Any]) -> bool:
    """Return whether a message is a schedulable tool call with a valid id."""

    return (
        "id" in message
        and _valid_request_id(message.get("id"))
        and message.get("method") == "tools/call"
    )


async def _handle_and_write(
    server: MCPServer,
    message: Mapping[str, Any],
    *,
    writer: TextIO | None,
    max_message_bytes: int,
    lock: asyncio.Lock,
) -> None:
    """Handle one parsed message and write its optional response."""

    async def send_notification(notification: dict[str, JSONValue]) -> None:
        await _write_response(
            notification,
            writer=writer,
            max_message_bytes=max_message_bytes,
            lock=lock,
        )

    response = await server.handle(message, notification_sender=send_notification)
    if response is not None:
        await _write_response(
            response,
            writer=writer,
            max_message_bytes=max_message_bytes,
            lock=lock,
        )


async def _write_response(
    response: dict[str, JSONValue],
    *,
    writer: TextIO | None,
    max_message_bytes: int,
    lock: asyncio.Lock,
) -> None:
    """Serialize and emit one size-bounded response under the writer lock."""

    encoded = _json_text(response)
    if len(encoded.encode("utf-8")) > max_message_bytes:
        if "id" not in response:
            print("Samsarix Core dropped an oversized MCP notification", file=sys.stderr)
            return
        fallback_id = response.get("id")
        encoded = _json_text(
            MCPServer._error(fallback_id, _INTERNAL_ERROR, "MCP response exceeds limit")
        )
    async with lock:
        if writer is None:
            sys.stdout.buffer.write((encoded + "\n").encode("utf-8"))
            sys.stdout.buffer.flush()
        else:
            writer.write(encoded + "\n")
            writer.flush()


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
    return (
        isinstance(value, (str, int, float))
        and not isinstance(value, bool)
        and (not isinstance(value, float) or math.isfinite(value))
    )


def _request_progress_token(params: Mapping[str, Any]) -> str | int | float | None:
    if "_meta" not in params:
        return None
    metadata = params.get("_meta")
    if not isinstance(metadata, Mapping):
        raise _InvalidParams("tools/call _meta must be an object")
    if "progressToken" not in metadata:
        return None
    token = metadata.get("progressToken")
    if not _valid_request_id(token):
        raise _InvalidParams("progressToken must be a finite string or number")
    return cast(str | int | float, token)


class _InvalidParams(ValueError):
    """Private control-flow exception for safe JSON-RPC parameter errors."""
