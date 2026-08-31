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
from collections.abc import Awaitable, Callable
from datetime import timedelta
from functools import partial
from importlib.metadata import version
from pathlib import Path
from types import TracebackType
from typing import Any, cast

SDK_VERSIONS = ("1.29.1", "2.1.1")
PROTOCOL = "2025-11-25"
MODERN_PROTOCOL = "2026-07-28"
SERVER_INFO = "io.modelcontextprotocol/serverInfo"


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


def check_modern_result(result: Any, name: str) -> dict[str, Any]:
    data = wire(result)
    require(data.get("resultType") == "complete", "missing modern complete result")
    require(data.get("_meta", {}).get(SERVER_INFO, {}).get("name") == name, "wrong modern identity")
    return data


async def journey(session: Any, logs: list[dict[str, Any]], *, modern: bool = False) -> None:
    """Use SDK methods and models, never this repository's JSON-RPC encoder/parser."""

    if modern:
        require(session.discover_result is not None, "modern client fell back to initialization")
        discovered = check_modern_result(session.discover_result, "samsarix-inventory-example")
        require(discovered.get("supportedVersions") == [MODERN_PROTOCOL], "wrong modern versions")
        require(
            "tasks" not in discovered["capabilities"], "legacy tasks advertised to modern client"
        )
    else:
        initialized = wire(await session.initialize())
        require(initialized.get("protocolVersion") == PROTOCOL, "unexpected negotiated protocol")
        require(
            initialized["serverInfo"]["name"] == "samsarix-inventory-example",
            "wrong example server",
        )
        await session.send_ping()
    catalog_result = await session.list_tools()
    catalog = wire(catalog_result)
    if modern:
        check_modern_result(catalog_result, "samsarix-inventory-example")
        require(
            catalog.get("ttlMs") == 0 and catalog.get("cacheScope") == "private",
            "unsafe cache hints",
        )
        require(
            [tool["name"] for tool in catalog["tools"]]
            == sorted(tool["name"] for tool in catalog["tools"]),
            "nondeterministic tool order",
        )
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
        if modern:
            check_modern_result(result, "samsarix-inventory-example")
        validator(tools["check_inventory"]["outputSchema"]).validate(
            wire(result)["structuredContent"]
        )

    if not modern:
        await session.set_logging_level("error")
    else:
        require(not logs, "modern request without logLevel emitted a log")
    sentinel = "synthetic-client-private-sentinel"
    options = {"meta": {"io.modelcontextprotocol/logLevel": "error"}} if modern else {}
    invalid_result = await session.call_tool(
        "check_inventory", {"sku": {"private": sentinel}}, **options
    )
    invalid = wire(invalid_result)
    if modern:
        check_modern_result(invalid_result, "samsarix-inventory-example")
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
    if modern:
        # This error has no logLevel: an earlier request must not enable its log.
        await session.call_tool("check_inventory", {"sku": {"private": sentinel}})
        require(len(logs) == 1, "modern log level leaked between requests")
        check_modern_result(await session.list_tools(), "samsarix-inventory-example")
    else:
        await session.send_ping()


async def run_client(
    server_python: Path, example: Path, sdk_version: str, *, modern: bool = False
) -> None:
    sdk = importlib.import_module("mcp")
    anyio = importlib.import_module("anyio")
    logs: list[dict[str, Any]] = []

    async def logging_callback(params: Any) -> None:
        logs.append(wire(params))

    bootstrap = Path(__file__).with_name("mcp_client_server.py")
    parameters = sdk.StdioServerParameters(
        command=str(server_python),
        args=["-I", str(bootstrap), str(example), *(["--modern"] if modern else [])],
    )
    # AnyIO's outer scope encloses both transport/session entry and cleanup in the
    # same task. The SDK owns and reaps its subprocess on context exit.
    with anyio.fail_after(45):
        if sdk_version.startswith("2."):
            client_type = importlib.import_module("mcp.client.client").Client
            # Exercise the current client's default discover-to-initialize fallback,
            # not a forced legacy mode or a hand-built initialization exchange.
            async with client_type(parameters, logging_callback=logging_callback) as client:
                if not modern:
                    require(
                        client.session.discover_result is None,
                        "unexpected modern protocol adoption",
                    )
                await journey(client.session, logs, modern=modern)
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


class RecordedSend:
    """Observe the SDK's typed outgoing request ID without guessing or changing it."""

    def __init__(self, stream: Any) -> None:
        self.stream = stream
        self.request_ids: list[str | int] = []

    async def send(self, message: Any) -> None:
        data = wire(message.message)
        if (
            data.get("method") == "tools/call"
            and data.get("params", {}).get("name") == "wait_for_cancellation"
        ):
            identifier = data.get("id")
            require(type(identifier) in (str, int), "SDK request ID was not observable")
            self.request_ids.append(cast(str | int, identifier))
        await self.stream.send(message)

    async def __aenter__(self) -> RecordedSend:
        await self.stream.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.stream.__aexit__(exc_type, exc, traceback)


async def recovered_state(session: Any, count: int) -> Any:
    """Require cleanup convergence, not an atomic semaphore/counter update.

    The next tool can acquire the released execution slot before the cancelled
    invoke coroutine resumes to record its terminal counter and release admission.
    Only that precise transient is allowed; the caller bounds the entire check.
    """

    expected = {
        "active": 0,
        "cancelled": count,
        "completed": 0,
        "runtime_cancelled": count,
        "runtime_timed_out": 0,
        "in_flight": 1,
        "pending": 1,
    }
    for _ in range(100):
        result = await session.call_tool("cancellation_state", {})
        actual = wire(result).get("structuredContent")
        if actual == expected:
            check_result(result, expected)
            return result
        if (
            isinstance(actual, dict)
            and actual.get("runtime_cancelled") in (count - 1, count)
            and actual.get("pending") in (1, 2)
        ):
            transient = {
                **expected,
                "runtime_cancelled": actual["runtime_cancelled"],
                "pending": actual["pending"],
            }
            check_result(result, transient)
        else:
            check_result(result, expected)
        await asyncio.sleep(0.01)
    raise RuntimeError("cancellation cleanup counters did not converge")


async def cancellation_journey(
    session: Any,
    explicit_cancel: Callable[[], Awaitable[None]] | None,
    *,
    timeout: float = 5,
    modern: bool = False,
) -> None:
    if modern:
        discovered = check_modern_result(session.discover_result, "samsarix-cancellation-fixture")
        require(
            discovered.get("supportedVersions") == [MODERN_PROTOCOL], "wrong cancellation protocol"
        )
    else:
        initialized = wire(await session.initialize())
        require(initialized.get("protocolVersion") == PROTOCOL, "unexpected cancellation protocol")
        require(
            initialized["serverInfo"]["name"] == "samsarix-cancellation-fixture",
            "wrong cancellation fixture",
        )
    catalog = wire(await session.list_tools())
    require(
        {tool["name"] for tool in catalog["tools"]}
        == {"wait_for_cancellation", "cancellation_state"},
        "missing cancellation fixture tools",
    )

    async def progress(
        started: asyncio.Event,
        updates: list[tuple[float, float | None, str | None]],
        value: float,
        total: float | None,
        message: str | None,
    ) -> None:
        updates.append((value, total, message))
        started.set()

    for count in (1, 2):
        started = asyncio.Event()
        updates: list[tuple[float, float | None, str | None]] = []

        call = asyncio.create_task(
            session.call_tool(
                "wait_for_cancellation",
                {"private_input": "synthetic-cancellation-private-sentinel"},
                progress_callback=partial(progress, started, updates),
            )
        )
        try:
            # Observe actual tool execution, not an arbitrary sleep or guessed ID.
            await asyncio.wait_for(started.wait(), timeout)
            require(not call.done(), "cancellation call completed before cancellation")
            if explicit_cancel is not None:
                await explicit_cancel()
            call.cancel()
            try:
                await asyncio.wait_for(call, timeout)
            except asyncio.CancelledError:
                pass
            else:
                raise RuntimeError("client cancellation did not propagate")

            # This call needs the same sole slot. A locally cancelled client task
            # alone cannot pass: the server must stop the work and release capacity.
            recovered = await asyncio.wait_for(recovered_state(session, count), timeout)
            require(
                updates == [(1, 2, "started")],
                "unexpected cancellation progress or private content",
            )
            if modern:
                check_modern_result(recovered, "samsarix-cancellation-fixture")
                await session.list_tools()
            else:
                await session.send_ping()
        finally:
            if not call.done():
                call.cancel()
            await asyncio.wait_for(asyncio.gather(call, return_exceptions=True), timeout)


async def run_cancellation_client(
    server_python: Path, sdk_version: str, *, modern: bool = False
) -> None:
    sdk = importlib.import_module("mcp")
    types = importlib.import_module("mcp.types")
    anyio = importlib.import_module("anyio")
    stdio_client = importlib.import_module("mcp.client.stdio").stdio_client
    scripts = Path(__file__).parent
    parameters = sdk.StdioServerParameters(
        command=str(server_python),
        args=[
            "-I",
            str(scripts / "mcp_client_server.py"),
            str(scripts / "mcp_cancellation_fixture.py"),
            *(["--modern"] if modern else []),
        ],
    )
    with anyio.fail_after(20):
        async with stdio_client(parameters) as (read, write):
            recorded = RecordedSend(write)
            async with sdk.ClientSession(
                read, recorded if sdk_version.startswith("1.") else write
            ) as session:
                if modern:
                    # A direct modern discovery/adoption; no initialize fallback.
                    session.adopt(
                        types.DiscoverResult.model_validate(
                            await session.send_discover(MODERN_PROTOCOL)
                        )
                    )

                async def notify_cancel() -> None:
                    require(bool(recorded.request_ids), "cancellation request ID was not observed")
                    notification = types.CancelledNotification(
                        params=types.CancelledNotificationParams(
                            requestId=recorded.request_ids[-1], reason="verification cancellation"
                        )
                    )
                    await session.send_notification(types.ClientNotification(notification))

                await cancellation_journey(
                    session, notify_cancel if sdk_version.startswith("1.") else None, modern=modern
                )


async def run_journeys(server_python: Path, sdk_version: str, *, modern: bool = False) -> None:
    example = Path(__file__).parents[1] / "examples" / "mcp_inventory_server.py"
    await run_client(server_python, example, sdk_version, modern=modern)
    await run_cancellation_client(server_python, sdk_version, modern=modern)


def run_client_process(command: list[str], workspace: Path, *, timeout: float = 60) -> None:
    """Bound the checker; the SDK server has its own independent lifetime watchdog."""

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
                    # SDK-created server sessions may be outside this group.
                    # mcp_client_server.py independently bounds their lifetime.
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=10)


def verify(wheel: Path, sdk_version: str, *, modern: bool = False) -> None:
    require(sdk_version in SDK_VERSIONS, "unsupported SDK pin")
    require(not modern or sdk_version == "2.1.1", "modern verification requires SDK 2.1.1")
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
                *(["--modern"] if modern else []),
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
                "protocol": MODERN_PROTOCOL if modern else PROTOCOL,
                "wheel": wheel.name,
                "sha256": digest.hexdigest(),
                "result": "passed",
                "cancellation": (
                    "explicit_sdk_notification"
                    if sdk_version.startswith("1.")
                    else "automatic_sdk_notification"
                ),
            }
        )
    )


def main() -> None:
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--client":
        asyncio.run(run_journeys(Path(sys.argv[2]), sys.argv[3], modern="--modern" in sys.argv[4:]))
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path, nargs="?", help="exact wheel, or the sole dist/*.whl")
    parser.add_argument("--sdk-version", required=True, choices=SDK_VERSIONS)
    parser.add_argument(
        "--modern", action="store_true", help="require opt-in MCP 2026-07-28 using SDK 2.1.1"
    )
    arguments = parser.parse_args()
    wheel = arguments.wheel
    if wheel is None:
        candidates = list(Path("dist").glob("*.whl"))
        if len(candidates) != 1:
            parser.error("dist/ must contain exactly one wheel; pass an explicit artifact path")
        wheel = candidates[0]
    verify(wheel, arguments.sdk_version, modern=arguments.modern)


if __name__ == "__main__":
    main()
