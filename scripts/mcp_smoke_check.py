# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify the documented MCP example through real UTF-8 subprocess pipes."""

from __future__ import annotations

import asyncio
import json
import sys
from contextlib import suppress
from pathlib import Path
from typing import Any, cast


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


async def exchange(
    process: asyncio.subprocess.Process, message: dict[str, Any]
) -> list[dict[str, Any]]:
    """Write one request and read bounded notifications until its exact response."""

    if process.stdin is None or process.stdout is None:
        raise RuntimeError("missing subprocess pipes")
    process.stdin.write((json.dumps(message, ensure_ascii=False) + "\n").encode("utf-8"))
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
            require("error" not in response and "result" in response, "MCP request failed")
            return messages
        require(
            response.get("method") in {"notifications/progress", "notifications/message"},
            "unexpected notification",
        )
    raise RuntimeError("too many notifications before the response")


async def journey(process: asyncio.subprocess.Process) -> None:
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


async def verify_server(example: Path, *, timeout: float = 20) -> None:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        str(example),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        limit=65_536,
    )
    try:
        await asyncio.wait_for(journey(process), timeout=timeout)
    finally:
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
        await asyncio.wait_for(process.wait(), timeout=5)


def main() -> None:
    example = Path(__file__).resolve().parents[1] / "examples" / "mcp_inventory_server.py"
    asyncio.run(verify_server(example))
    print("MCP subprocess: discovery, sync Unicode, validation, async progress, EOF OK")


if __name__ == "__main__":
    main()
