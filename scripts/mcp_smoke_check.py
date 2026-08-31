# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify the documented MCP example through real UTF-8 subprocess pipes."""

from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import tempfile
from collections.abc import Awaitable, Callable
from contextlib import closing, suppress
from functools import partial
from pathlib import Path
from typing import Any, cast


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def exchange(
    process: asyncio.subprocess.Process,
    message: dict[str, Any],
    *,
    expected_error_code: int | None = None,
) -> list[dict[str, Any]]:
    """Write one request and read bounded notifications until its exact response."""

    if process.stdin is None or process.stdout is None:
        raise RuntimeError("missing subprocess pipes")
    process.stdin.write((json.dumps(message, ensure_ascii=True) + "\n").encode("utf-8"))
    await process.stdin.drain()
    messages: list[dict[str, Any]] = []
    for _ in range(16):
        line = await process.stdout.readline()
        require(bool(line) and line.endswith(b"\n"), "missing newline-delimited MCP response")
        decoded = json.loads(line.decode("utf-8"))
        require(isinstance(decoded, dict), "MCP response is not an object")
        response = cast(dict[str, Any], decoded)
        require(response.get("jsonrpc") == "2.0", "non-protocol stdout")
        messages.append(response)
        if "id" in response:
            require(response["id"] == message["id"], "wrong or duplicate response ID")
            if expected_error_code is None:
                require("error" not in response and "result" in response, "MCP request failed")
            else:
                require(
                    response.get("error", {}).get("code") == expected_error_code
                    and "result" not in response,
                    "malformed MCP request was not safely rejected",
                )
            return messages
        require(
            response.get("method") in {"notifications/progress", "notifications/message"},
            "unexpected notification",
        )
    raise RuntimeError("too many notifications before the response")


async def journey(process: asyncio.subprocess.Process) -> None:
    malformed_methods: tuple[Any, ...] = ([], {})
    for method in malformed_methods:
        await exchange(
            process,
            {"jsonrpc": "2.0", "id": "malformed", "method": method},
            expected_error_code=-32600,
        )
    await exchange(process, {"jsonrpc": "2.0", "id": "\ud800", "method": "ping"})
    initialized = await exchange(
        process,
        {
            "jsonrpc": "2.0",
            "id": "init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "installed-wheel-smoke", "version": "1"},
            },
        },
    )
    require(initialized[-1]["result"]["protocolVersion"] == "2025-11-25", "wrong protocol")
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("missing subprocess pipes")
    process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
    await process.stdin.drain()
    discovered = await exchange(process, {"jsonrpc": "2.0", "id": "list", "method": "tools/list"})
    tools = discovered[-1]["result"]["tools"]
    require(
        {tool["name"] for tool in tools}
        == {"check_inventory", "reserve_inventory", "audit_inventory"},
        "documented tools were not discovered",
    )
    for identifier, sku, count in (
        ("known", "cable-usb-c", 18),
        ("unicode", "caf\u00e9-\u6771\u4eac-\U0001f680\n", 0),
    ):
        result = await exchange(
            process,
            {
                "jsonrpc": "2.0",
                "id": identifier,
                "method": "tools/call",
                "params": {"name": "check_inventory", "arguments": {"sku": sku}},
            },
        )
        require(result[-1]["result"].get("isError") is False, "inventory invocation failed")
        require(
            result[-1]["result"]["structuredContent"] == {"sku": sku, "available": count},
            "wrong inventory result",
        )
    invalid = await exchange(
        process,
        {
            "jsonrpc": "2.0",
            "id": "invalid",
            "method": "tools/call",
            "params": {"name": "check_inventory", "arguments": {"sku": 123}},
        },
    )
    require(invalid[-1]["result"].get("isError") is True, "invalid MCP input was accepted")
    require(len(invalid) == 2, "expected one log before invalid-input response")
    require(invalid[0].get("method") == "notifications/message", "missing operational log")
    require(invalid[0]["params"]["level"] == "error", "unexpected operational log level")
    require(
        set(invalid[0]["params"]["data"])
        == {"event", "tool", "invocationId", "status", "durationMs"},
        "operational log contains unexpected fields",
    )
    progress = await exchange(
        process,
        {
            "jsonrpc": "2.0",
            "id": "audit",
            "method": "tools/call",
            "params": {
                "name": "audit_inventory",
                "arguments": {"skus": ["cable-usb-c", "missing"]},
                "_meta": {"progressToken": "smoke-progress"},
            },
        },
    )
    require(len(progress) == 3, "missing progress or extra protocol output")
    for position, notification in enumerate(progress[:-1], start=1):
        params = notification["params"]
        require(
            params["progressToken"] == "smoke-progress"
            and params["progress"] == position
            and params["total"] == 2,
            "progress is uncorrelated or out of order",
        )
    require(
        progress[-1]["result"].get("isError") is False
        and progress[-1]["result"]["structuredContent"] == {"checked": 2, "known": 1},
        "audit result differs",
    )
    process.stdin.close()
    # EOF must drain/close without extra responses, blocked reads or orphaned workers.
    require(await process.stdout.read(1) == b"", "unexpected trailing stdout")
    require(await process.wait() == 0, "server did not exit cleanly on EOF")


async def verify_server(
    example: Path,
    *,
    timeout: float = 20,
    arguments: tuple[str, ...] = (),
    conversation: Callable[[asyncio.subprocess.Process], Awaitable[None]] | None = None,
) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(example),
        *arguments,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        limit=65_536,
    )
    try:
        await asyncio.wait_for((conversation or journey)(process), timeout=timeout)
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await asyncio.wait_for(process.wait(), timeout=5)


async def sqlite_journey(
    process: asyncio.subprocess.Process,
    *,
    modern: bool,
    phase: str,
    available: int,
) -> None:
    """Verify one host session's exact catalog, read/write policy and business results."""

    metadata = (
        {
            "io.modelcontextprotocol/protocolVersion": "2026-07-28",
            "io.modelcontextprotocol/clientCapabilities": {},
        }
        if modern
        else {}
    )

    async def request(method: str, params: dict[str, Any]) -> dict[str, Any]:
        if modern:
            params = {**params, "_meta": metadata}
        messages = await exchange(
            process, {"jsonrpc": "2.0", "id": method, "method": method, "params": params}
        )
        require(len(messages) == 1, "SQLite example emitted unsolicited notifications")
        result = cast(dict[str, Any], messages[-1]["result"])
        if modern:
            require(result.get("resultType") == "complete", "incomplete modern SQLite result")
        return result

    if modern:
        discovery = await request("server/discover", {})
        require(discovery["supportedVersions"] == ["2026-07-28"], "wrong SQLite modern protocol")
    else:
        initialized = await request(
            "initialize",
            {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "sqlite-wheel-smoke", "version": "1"},
            },
        )
        require(initialized["protocolVersion"] == "2025-11-25", "wrong SQLite legacy protocol")
        require(process.stdin is not None, "missing SQLite stdin")
        assert process.stdin is not None  # Narrowing only; require above is the actual check.
        process.stdin.write(b'{"jsonrpc":"2.0","method":"notifications/initialized"}\n')
        await process.stdin.drain()
    catalog = (await request("tools/list", {}))["tools"]
    require(
        len(catalog) == 2
        and {tool["name"] for tool in catalog} == {"check_inventory", "reserve_inventory"},
        "wrong SQLite catalog",
    )
    writer = next(tool for tool in catalog if tool["name"] == "reserve_inventory")
    require(
        writer["annotations"]
        == {
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": True,
            "openWorldHint": False,
        },
        "SQLite writer annotations are misleading",
    )
    require(
        set(writer["inputSchema"]["properties"]) == {"sku", "quantity", "request_id"}
        and set(
            next(tool for tool in catalog if tool["name"] == "check_inventory")["inputSchema"][
                "properties"
            ]
        )
        == {"sku"},
        "SQLite host path exposed in tool schema",
    )

    async def call(name: str, arguments: dict[str, Any], expected: dict[str, Any]) -> None:
        result = await request("tools/call", {"name": name, "arguments": arguments})
        require(result.get("isError") is False, "SQLite tool failed")
        require(result.get("structuredContent") == expected, "wrong SQLite business result")
        content = result.get("content")
        if not (
            isinstance(content, list)
            and len(content) == 1
            and isinstance(content[0], dict)
            and content[0].get("type") == "text"
        ):
            raise RuntimeError("SQLite text fallback is missing")
        require(json.loads(content[0]["text"]) == expected, "SQLite text fallback disagrees")

    await call("check_inventory", {"sku": "cable-usb-c"}, {"available": available})
    await call("check_inventory", {"sku": "unknown"}, {"available": None})
    arguments: dict[str, Any] = {"sku": "cable-usb-c", "quantity": 2, "request_id": "order-001"}
    if phase == "denied":
        denied = await request("tools/call", {"name": "reserve_inventory", "arguments": arguments})
        require(
            denied.get("isError") is True and denied["_meta"]["com.samsarix/status"] == "denied",
            "SQLite write/replay was not denied by default",
        )
    else:
        expected = {"status": "reserved", "available": 3}
        await call("reserve_inventory", arguments, expected)
        await call("reserve_inventory", arguments, expected)
        await call(
            "reserve_inventory",
            {**arguments, "quantity": 3},
            {"status": "idempotency_conflict", "available": None},
        )
        await call(
            "reserve_inventory",
            {**arguments, "request_id": "order-002"},
            {"status": "capacity_exceeded", "available": None},
        )
        invalid = await request(
            "tools/call",
            {"name": "reserve_inventory", "arguments": {**arguments, "quantity": True}},
        )
        require(
            invalid.get("isError") is True
            and invalid["_meta"]["com.samsarix/status"] == "invalid_arguments",
            "SQLite invalid argument was accepted",
        )
        await call("check_inventory", {"sku": "cable-usb-c"}, {"available": 3})
    if process.stdin is None or process.stdout is None:
        raise RuntimeError("missing SQLite pipes")
    process.stdin.close()
    require(await process.stdout.read(1) == b"", "SQLite trailing stdout")
    require(await process.wait() == 0, "SQLite process did not close cleanly")


async def verify_sqlite_example(example: Path) -> None:
    """Check actual disk state across independently launched legacy and modern hosts."""

    with tempfile.TemporaryDirectory(prefix="samsarix-mcp-sqlite-") as directory:
        for modern in (False, True):
            database = Path(directory) / f"inventory space-\u6771\u4eac-{modern}.sqlite3"
            initialize = await asyncio.create_subprocess_exec(
                sys.executable,
                "-I",
                str(example),
                "init",
                str(database),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                output, error = await asyncio.wait_for(initialize.communicate(), timeout=10)
                require(initialize.returncode == 0 and not error, "SQLite initialization failed")
                require(
                    json.loads(output)
                    == {"status": "created", "sku": "cable-usb-c", "available": 5},
                    "wrong SQLite initialization result",
                )
            finally:
                if initialize.returncode is None:
                    with suppress(ProcessLookupError):
                        initialize.kill()
                await asyncio.wait_for(initialize.wait(), timeout=5)
            for phase, available in (("denied", 5), ("write", 5), ("replay", 3), ("denied", 3)):
                arguments: tuple[str, ...] = ("serve", str(database), "--max-requests", "1")
                if phase != "denied":
                    arguments += ("--allow-reservations",)
                if modern:
                    arguments += ("--modern",)
                await verify_server(
                    example,
                    arguments=arguments,
                    conversation=partial(
                        sqlite_journey, modern=modern, phase=phase, available=available
                    ),
                )
                with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as db:
                    stock = db.execute("SELECT available FROM inventory").fetchall()
                    rows = db.execute(
                        "SELECT request_id, quantity, status, available FROM reservations"
                    ).fetchall()
                untouched = phase == "denied" and available == 5
                require(stock == [(5 if untouched else 3,)], "SQLite persisted stock differs")
                require(
                    rows == ([] if untouched else [("order-001", 2, "reserved", 3)]),
                    "SQLite ledger differs or contains duplicate writes",
                )


def main() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "mcp_inventory_server.py"
    asyncio.run(verify_server(example))
    print("MCP subprocess: malformed frames, discovery, Unicode, validation, progress, EOF OK")
    asyncio.run(verify_sqlite_example(example.with_name("sqlite_reservations.py")))
    print("SQLite MCP: host-gated writes, durable replay, conflicts, ledger cap, both protocols OK")


if __name__ == "__main__":
    main()
