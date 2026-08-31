# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Verify an installed Core wheel using a separately installed official MCP client.

Install one documented, pinned SDK in the invoking environment first. Only the
server wheel is installed by this command, offline into a fresh isolated venv.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import signal
import subprocess
import sys
import tempfile
from datetime import timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any, cast

SDK_VERSIONS = ("1.29.1", "2.1.1")
PROTOCOL = "2025-11-25"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def wire(model: Any) -> dict[str, Any]:
    """Normalize the SDK's v1 camelCase/v2 snake_case Python names via wire aliases."""

    result = model.model_dump(mode="json", by_alias=True, exclude_none=True)
    require(isinstance(result, dict), "SDK returned a non-object model")
    return cast(dict[str, Any], result)


def check_result(result: Any, expected: dict[str, Any]) -> None:
    data = wire(result)
    require(data.get("isError") is False, "official client received a tool failure")
    require(data.get("structuredContent") == expected, "incorrect structured tool result")
    content = data.get("content", [])
    require(len(content) == 1 and content[0].get("type") == "text", "missing text fallback")
    require(json.loads(content[0]["text"]) == expected, "text/structured result disagreement")


async def journey(session: Any, logs: list[dict[str, Any]]) -> None:
    """Use SDK methods and models, never this repository's JSON-RPC encoder/parser."""

    initialized = wire(await session.initialize())
    require(initialized.get("protocolVersion") == PROTOCOL, "unexpected negotiated protocol")
    require(
        initialized["serverInfo"]["name"] == "samsarix-inventory-example",
        "wrong example server",
    )
    await session.send_ping()
    catalog = wire(await session.list_tools())
    tools = {tool["name"]: tool for tool in catalog["tools"]}
    require(
        set(tools) == {"check_inventory", "reserve_inventory", "audit_inventory"},
        "official client discovered the wrong tools",
    )
    validator = importlib.import_module("jsonschema").Draft202012Validator
    for tool in tools.values():
        for schema_name in ("inputSchema", "outputSchema"):
            validator.check_schema(tool[schema_name])
        require(tool["annotations"]["readOnlyHint"] is True, "incorrect read-only hint")
        require(tool["annotations"]["openWorldHint"] is False, "incorrect world-boundary hint")

    for sku, available in (("cable-usb-c", 18), ("caf\u00e9-\u6771\u4eac-\U0001f680\n", 0)):
        result = await session.call_tool("check_inventory", {"sku": sku})
        check_result(result, {"sku": sku, "available": available})
        validator(tools["check_inventory"]["outputSchema"]).validate(
            wire(result)["structuredContent"]
        )

    await session.set_logging_level("error")
    sentinel = "synthetic-client-private-sentinel"
    invalid = wire(await session.call_tool("check_inventory", {"sku": {"private": sentinel}}))
    require(invalid.get("isError") is True, "invalid input accepted through official client")
    require(invalid["_meta"]["com.samsarix/status"] == "invalid_arguments", "wrong error status")
    require(len(logs) == 1, "expected one error log")
    require(logs[0]["level"] == "error", "incorrect log level")
    require(
        set(logs[0]["data"]) == {"event", "tool", "invocationId", "status", "durationMs"},
        "operational log is not content-free",
    )
    require(sentinel not in json.dumps([invalid, logs]), "private input entered an error or log")

    updates: list[tuple[float, float | None, str | None]] = []

    async def progress(value: float, total: float | None, message: str | None) -> None:
        updates.append((value, total, message))

    audit = await session.call_tool(
        "audit_inventory",
        {"skus": ["cable-usb-c", "missing"]},
        progress_callback=progress,
    )
    check_result(audit, {"checked": 2, "known": 1})
    validator(tools["audit_inventory"]["outputSchema"]).validate(wire(audit)["structuredContent"])
    require(
        updates
        == [(1, 2, "Checked 1 of 2 inventory records"), (2, 2, "Checked 2 of 2 inventory records")],
        "official client missed or miscorrelated progress",
    )
    empty = await session.call_tool("audit_inventory", {"skus": []})
    check_result(empty, {"checked": 0, "known": 0})
    require(len(logs) == 1, "error-level filter admitted successful calls")
    await session.send_ping()


async def run_client(server_python: Path, example: Path, sdk_version: str) -> None:
    sdk = importlib.import_module("mcp")
    anyio = importlib.import_module("anyio")
    logs: list[dict[str, Any]] = []

    async def logging_callback(params: Any) -> None:
        logs.append(wire(params))

    parameters = sdk.StdioServerParameters(command=str(server_python), args=["-I", str(example)])
    # AnyIO's outer scope encloses both transport/session entry and cleanup in the
    # same task. The SDK owns and reaps its subprocess on context exit.
    with anyio.fail_after(45):
        if sdk_version.startswith("2."):
            client_type = importlib.import_module("mcp.client.client").Client
            # Exercise the current client's default discover-to-initialize fallback,
            # not a forced legacy mode or a hand-built initialization exchange.
            async with client_type(parameters, logging_callback=logging_callback) as client:
                require(
                    client.session.discover_result is None, "unexpected modern protocol adoption"
                )
                await journey(client.session, logs)
        else:
            stdio_client = importlib.import_module("mcp.client.stdio").stdio_client
            async with stdio_client(parameters) as (read, write):
                async with sdk.ClientSession(
                    read,
                    write,
                    read_timeout_seconds=timedelta(seconds=10),
                    logging_callback=logging_callback,
                ) as session:
                    await journey(session, logs)


def run_client_process(command: list[str], workspace: Path, *, timeout: float = 60) -> None:
    """Bound the checker and clean up its owned process tree if SDK cleanup stalls."""

    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen(
        command,
        cwd=workspace,
        start_new_session=sys.platform != "win32",
        creationflags=creationflags,
    )
    try:
        returncode = process.wait(timeout=timeout)
        if returncode:
            raise subprocess.CalledProcessError(returncode, command)
    finally:
        if process.poll() is None:
            if sys.platform == "win32":
                # Only the still-live checker PID created immediately above is
                # targeted. /T includes its server; no name-based global kills.
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    check=False,
                    timeout=10,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=10)


def verify(wheel: Path, sdk_version: str) -> None:
    require(sdk_version in SDK_VERSIONS, "unsupported SDK pin")
    require(version("mcp") == sdk_version, "installed SDK differs from requested pin")
    wheel = wheel.resolve(strict=True)
    require(wheel.is_file() and wheel.suffix == ".whl", "expected a wheel file")
    with tempfile.TemporaryDirectory(prefix="samsarix-official-server-") as temporary:
        workspace = Path(temporary)
        environment = workspace / "server"
        server_python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run(
            [sys.executable, "-I", "-m", "venv", str(environment)], check=True, timeout=120
        )
        subprocess.run(
            [
                str(server_python),
                "-I",
                "-m",
                "pip",
                "--isolated",
                "install",
                "--no-index",
                "--no-deps",
                str(wheel),
            ],
            cwd=workspace,
            check=True,
            timeout=120,
        )
        subprocess.run(
            [str(server_python), "-I", "-m", "pip", "check"],
            cwd=workspace,
            check=True,
            timeout=30,
        )
        isolation = subprocess.run(
            [
                str(server_python),
                "-I",
                "-c",
                "import importlib.util, samsarix_core; "
                "from importlib.metadata import requires; "
                "print(samsarix_core.__file__); "
                "raise SystemExit(importlib.util.find_spec('mcp') is not None "
                "or bool([r for r in requires('samsarix-core') or [] if 'extra ==' not in r]))",
            ],
            cwd=workspace,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        imported_path = Path(isolation.stdout.strip()).resolve(strict=True)
        require(
            imported_path.is_relative_to(environment.resolve()), "server imported source checkout"
        )
        run_client_process(
            [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--client",
                str(server_python),
                sdk_version,
            ],
            workspace,
        )
    digest = hashlib.sha256()
    with wheel.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(65_536), b""):
            digest.update(chunk)
    print(
        json.dumps(
            {
                "sdk": sdk_version,
                "protocol": PROTOCOL,
                "wheel": wheel.name,
                "sha256": digest.hexdigest(),
                "result": "passed",
            }
        )
    )


def main() -> None:
    if len(sys.argv) == 4 and sys.argv[1] == "--client":
        example = Path(__file__).resolve().parents[1] / "examples" / "mcp_inventory_server.py"
        asyncio.run(run_client(Path(sys.argv[2]), example, sys.argv[3]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="?", help="exact wheel, or the sole dist/*.whl")
    parser.add_argument("--sdk-version", required=True, choices=SDK_VERSIONS)
    arguments = parser.parse_args()
    wheel = arguments.wheel
    if wheel is None:
        candidates = list(Path("dist").glob("*.whl"))
        if len(candidates) != 1:
            parser.error("dist/ must contain exactly one wheel; pass an explicit artifact path")
        wheel = candidates[0]
    verify(wheel, arguments.sdk_version)


if __name__ == "__main__":
    main()
