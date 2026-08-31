# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import copy
import importlib.util
import json
import runpy
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_mcp_client.py"


def load_script(name="verify_mcp_client"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT.with_name(f"{name}.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Model:
    def __init__(self, data):
        self.data = data

    def model_dump(self, **kwargs):
        assert kwargs == {"mode": "json", "by_alias": True, "exclude_none": True}
        return copy.deepcopy(self.data)


def result(data):
    return Model(
        {
            "isError": False,
            "structuredContent": data,
            "content": [{"type": "text", "text": json.dumps(data)}],
        }
    )


def test_sdk_wire_aliases_and_text_fallback():
    script = load_script()
    script.check_result(
        result({"sku": "caf\u00e9\n", "available": 0}), {"sku": "caf\u00e9\n", "available": 0}
    )


@pytest.mark.parametrize(
    "mutation,message",
    [
        (lambda data: data.update(isError=True), "tool failure"),
        (lambda data: data.update(structuredContent={"available": 999}), "structured tool result"),
        (lambda data: data.update(content=[]), "text fallback"),
        (lambda data: data["content"][0].update(text='{"available":999}'), "disagreement"),
    ],
)
def test_checker_rejects_incorrect_results(mutation, message):
    value = result({"available": 18})
    mutation(value.data)
    with pytest.raises(RuntimeError, match=message):
        load_script().check_result(value, {"available": 18})


class Validator:
    """No SDK dependency in unit tests; the real CI journey loads jsonschema."""

    def __init__(self, schema):
        pass

    @staticmethod
    def check_schema(schema):
        assert schema["type"] == "object"

    def validate(self, data):
        assert isinstance(data, dict)


class Session:
    def __init__(self, logs, fault=None):
        self.logs = logs
        self.fault = fault
        self.pings = 0

    async def initialize(self):
        return Model(
            {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": "samsarix-inventory-example"},
            }
        )

    async def send_ping(self):
        self.pings += 1

    async def list_tools(self):
        return Model(
            {
                "tools": [
                    {
                        "name": name,
                        "inputSchema": {"type": "object"},
                        "outputSchema": {"type": "object"},
                        "annotations": {"readOnlyHint": True, "openWorldHint": False},
                    }
                    for name in ("check_inventory", "reserve_inventory", "audit_inventory")
                ]
            }
        )

    async def set_logging_level(self, level):
        assert level == "error"

    async def call_tool(self, name, arguments, progress_callback=None):
        if name == "check_inventory":
            sku = arguments["sku"]
            if not isinstance(sku, str):
                data = dict.fromkeys(("event", "tool", "invocationId", "status", "durationMs"))
                if self.fault == "private_log":
                    data["arguments"] = arguments
                if self.fault == "private_value":
                    data["event"] = sku["private"]
                self.logs.append({"level": "error", "data": data})
                return Model(
                    {"isError": True, "_meta": {"com.samsarix/status": "invalid_arguments"}}
                )
            return result({"sku": sku, "available": 18 if sku == "cable-usb-c" else 0})
        skus = arguments["skus"]
        if progress_callback and self.fault != "missing_progress":
            for position in range(1, len(skus) + 1):
                await progress_callback(
                    position, len(skus), f"Checked {position} of {len(skus)} inventory records"
                )
        return result({"checked": len(skus), "known": int("cable-usb-c" in skus)})


@pytest.mark.asyncio
async def test_journey_checks_discovery_errors_progress_and_recovery(monkeypatch):
    script = load_script()
    monkeypatch.setattr(
        script.importlib, "import_module", lambda _: SimpleNamespace(Draft202012Validator=Validator)
    )
    logs = []
    session = Session(logs)
    await script.journey(session, logs)
    assert session.pings == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,message",
    [
        ("private_log", "content-free"),
        ("private_value", "private input"),
        ("missing_progress", "progress"),
    ],
)
async def test_journey_rejects_missing_progress_and_private_logs(monkeypatch, fault, message):
    script = load_script()
    monkeypatch.setattr(
        script.importlib, "import_module", lambda _: SimpleNamespace(Draft202012Validator=Validator)
    )
    logs = []
    with pytest.raises(RuntimeError, match=message):
        await script.journey(Session(logs, fault), logs)


def test_sdk_pin_mismatch_fails_before_install(monkeypatch, tmp_path):
    script = load_script()
    monkeypatch.setattr(script, "version", lambda _: "0.0.0")
    with pytest.raises(RuntimeError, match="differs from requested pin"):
        script.verify(tmp_path / "missing.whl", "2.1.1")


def test_unsupported_sdk_pin_fails_before_install(tmp_path):
    with pytest.raises(RuntimeError, match="unsupported SDK pin"):
        load_script().verify(tmp_path / "missing.whl", "2.0.0")


def test_modern_gate_rejects_legacy_sdk_before_install(tmp_path):
    with pytest.raises(RuntimeError, match="modern verification requires"):
        load_script().verify(tmp_path / "missing.whl", "1.29.1", modern=True)


class ModernSession(Session):
    def __init__(self, logs, fault=None):
        super().__init__(logs, fault)
        self.discover_result = self.stamp(
            Model({"supportedVersions": ["2026-07-28"], "capabilities": {"tools": {}}})
        )
        if fault == "fallback":
            self.discover_result = None

    def stamp(self, model):
        model.data["resultType"] = "complete"
        model.data.setdefault("_meta", {})["io.modelcontextprotocol/serverInfo"] = {
            "name": "samsarix-inventory-example"
        }
        if self.fault == "missing_type":
            del model.data["resultType"]
        if self.fault == "wrong_identity":
            model.data["_meta"]["io.modelcontextprotocol/serverInfo"]["name"] = "other"
        return model

    async def initialize(self):
        raise AssertionError("Modern journey must not initialize")

    async def send_ping(self):
        raise AssertionError("Modern journey must not ping")

    async def set_logging_level(self, level):
        raise AssertionError("Modern journey must not use connection-global log levels")

    async def list_tools(self):
        catalog = self.stamp(await super().list_tools())
        catalog.data.update(ttlMs=0, cacheScope="private")
        catalog.data["tools"].sort(key=lambda item: item["name"])
        if self.fault == "cache":
            catalog.data["cacheScope"] = "public"
        return catalog

    async def call_tool(self, name, arguments, progress_callback=None, *, meta=None):
        before = len(self.logs)
        result = self.stamp(await super().call_tool(name, arguments, progress_callback))
        if meta is None and self.fault != "leaked_log":
            del self.logs[before:]
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,message",
    [
        (None, None),
        ("fallback", "fell back"),
        ("missing_type", "complete result"),
        ("wrong_identity", "identity"),
        ("cache", "cache hints"),
        ("leaked_log", "log level leaked"),
    ],
)
async def test_modern_journey_requires_modern_contract_and_per_request_logs(
    monkeypatch, fault, message
):
    script = load_script()
    monkeypatch.setattr(
        script.importlib, "import_module", lambda _: SimpleNamespace(Draft202012Validator=Validator)
    )
    logs = []
    session = ModernSession(logs, fault)
    if fault:
        with pytest.raises(RuntimeError, match=message):
            await script.journey(session, logs, modern=True)
    else:
        await script.journey(session, logs, modern=True)
        assert len(logs) == 1


def test_server_bootstrap_forwards_arguments_and_restores_argv(tmp_path):
    script = load_script("mcp_client_server")
    fixture = tmp_path / "arguments.py"
    fixture.write_text("import sys\nassert sys.argv[1:] == ['--modern']\n", encoding="utf-8")
    original = sys.argv
    script.run_server(fixture, arguments=["--modern"])
    assert sys.argv is original


@pytest.mark.asyncio
@pytest.mark.parametrize("modern", [False, True])
@pytest.mark.parametrize("name", ["fixture", "inventory"])
async def test_examples_pass_new_constructor_option_only_when_requested(monkeypatch, modern, name):
    target = (
        SCRIPT.with_name("mcp_cancellation_fixture.py")
        if name == "fixture"
        else SCRIPT.parents[1] / "examples" / "mcp_inventory_server.py"
    )
    main = runpy.run_path(str(target))["main"]
    seen = []

    def constructor(runtime, **options):
        # An old published MCPServer cannot accept enable_modern, even if False.
        assert ("enable_modern" in options) is modern
        if modern:
            assert options["enable_modern"] is True
        seen.append(options)
        return SimpleNamespace(runtime=runtime)

    async def serve(server):
        await server.runtime.aclose()

    monkeypatch.setitem(main.__globals__, "MCPServer", constructor)
    monkeypatch.setitem(main.__globals__, "serve_stdio", serve)
    await main(enable_modern=modern)
    assert len(seen) == 1


@pytest.mark.parametrize("count", [0, 2])
def test_default_artifact_must_be_unambiguous(tmp_path, count):
    distribution = tmp_path / "dist"
    distribution.mkdir()
    for index in range(count):
        (distribution / f"candidate-{index}.whl").touch()
    completed = subprocess.run(
        [sys.executable, "-I", str(SCRIPT), "--sdk-version", "2.1.1"],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 2
    assert b"exactly one wheel" in completed.stderr


def test_checker_process_failure_is_not_reported_as_success(tmp_path):
    with pytest.raises(subprocess.CalledProcessError):
        load_script().run_client_process(
            [sys.executable, "-I", "-c", "raise SystemExit(7)"], tmp_path
        )


def test_checker_process_timeout_is_bounded_and_reaped(monkeypatch, tmp_path):
    script = load_script()
    popen = subprocess.Popen
    created = []

    def capture(*args, **kwargs):
        process = popen(*args, **kwargs)
        created.append(process)
        return process

    monkeypatch.setattr(script.subprocess, "Popen", capture)
    with pytest.raises(subprocess.TimeoutExpired):
        script.run_client_process(
            [sys.executable, "-I", "-c", "import time; time.sleep(30)"], tmp_path, timeout=0.5
        )
    assert created[0].poll() is not None


def test_checks_survive_python_optimization():
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-O",
            "-c",
            "import runpy; runpy.run_path("
            + repr(str(SCRIPT))
            + ")[\"require\"](False, 'sentinel-failure')",
        ],
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode != 0
    assert b"sentinel-failure" in completed.stderr


def test_independent_server_watchdog_exits_without_client_cleanup(tmp_path):
    example = tmp_path / "unresponsive_example.py"
    example.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
    bootstrap = SCRIPT.with_name("mcp_client_server.py")
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import runpy; from pathlib import Path; runpy.run_path("
            + repr(str(bootstrap))
            + ')["run_server"](Path('
            + repr(str(example))
            + "), timeout=0.2)",
        ],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 124


def test_server_watchdog_is_cancelled_on_normal_exit(tmp_path):
    example = tmp_path / "completed_example.py"
    example.write_text("print('normal-exit')\n", encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, "-I", str(SCRIPT.with_name("mcp_client_server.py")), str(example)],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == b"normal-exit"


class CancellationSession:
    def __init__(self, *, automatic=True, fault=None):
        self.automatic = automatic
        self.fault = fault
        self.active = 0
        self.cancelled = 0
        self.pings = 0
        self.inspections = {}

    async def initialize(self):
        return Model(
            {
                "protocolVersion": "2025-11-25",
                "serverInfo": {"name": "samsarix-cancellation-fixture"},
            }
        )

    async def list_tools(self):
        return Model(
            {"tools": [{"name": name} for name in ("wait_for_cancellation", "cancellation_state")]}
        )

    async def send_ping(self):
        self.pings += 1

    async def notify_cancel(self):
        self.active -= 1
        self.cancelled += 1

    async def call_tool(self, name, arguments, progress_callback=None):
        if name == "wait_for_cancellation":
            self.active += 1
            try:
                if self.fault != "missing_start":
                    message = (
                        arguments["private_input"]
                        if self.fault == "private_progress"
                        else "started"
                    )
                    await progress_callback(1, 2, message)
                if self.fault == "early_completion":
                    return result({"result": "finished"})
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                if self.automatic:
                    await self.notify_cancel()
                if self.fault == "swallowed_cancel":
                    return result({"result": "finished"})
                raise
        if self.fault == "leaked_slot":
            await asyncio.Event().wait()
        self.inspections[self.cancelled] = self.inspections.get(self.cancelled, 0) + 1
        settling = self.fault == "stuck_counters" or (
            self.fault == "settling_counters" and self.inspections[self.cancelled] == 1
        )
        return result(
            {
                "active": self.active,
                "cancelled": self.cancelled,
                "completed": 0,
                "runtime_cancelled": self.cancelled - int(settling),
                "runtime_timed_out": int(self.fault == "timed_out"),
                "in_flight": 1,
                "pending": 2 if settling else 1,
            }
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("automatic", [False, True])
async def test_cancellation_checker_requires_two_remote_cancellations_and_recovery(automatic):
    session = CancellationSession(automatic=automatic)
    await load_script().cancellation_journey(session, None if automatic else session.notify_cancel)
    assert session.cancelled == session.pings == 2
    assert session.active == 0


@pytest.mark.asyncio
async def test_local_cancellation_without_notification_is_not_remote_success():
    session = CancellationSession(automatic=False)
    with pytest.raises(RuntimeError, match="structured tool result"):
        await load_script().cancellation_journey(session, None)
    assert session.active == 1
    assert session.cancelled == 0


@pytest.mark.asyncio
async def test_cancellation_checker_waits_for_terminal_accounting_after_slot_release():
    session = CancellationSession(fault="settling_counters")
    await load_script().cancellation_journey(session, None)
    assert session.inspections == {1: 2, 2: 2}


@pytest.mark.asyncio
async def test_cancellation_checker_rejects_counters_that_never_finish_cleanup():
    with pytest.raises(asyncio.TimeoutError):
        await load_script().cancellation_journey(
            CancellationSession(fault="stuck_counters"), None, timeout=0.05
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fault,message",
    [
        ("early_completion", "completed before cancellation"),
        ("swallowed_cancel", "did not propagate"),
        ("timed_out", "structured tool result"),
        ("private_progress", "private content"),
    ],
)
async def test_cancellation_checker_rejects_false_success_and_private_progress(fault, message):
    with pytest.raises(RuntimeError, match=message):
        await load_script().cancellation_journey(CancellationSession(fault=fault), None)


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["missing_start", "leaked_slot"])
async def test_cancellation_checker_bounds_missing_start_and_leaked_capacity(fault):
    with pytest.raises(asyncio.TimeoutError):
        await load_script().cancellation_journey(
            CancellationSession(fault=fault), None, timeout=0.05
        )


@pytest.mark.asyncio
async def test_sdk_request_observer_preserves_messages_and_retains_only_target_ids():
    class Stream:
        def __init__(self):
            self.items = []
            self.closed = False

        async def send(self, item):
            self.items.append(item)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

    stream = Stream()
    items = [
        SimpleNamespace(message=Model(data))
        for data in (
            {"id": 10, "method": "initialize"},
            {
                "id": "observed-actual-id",
                "method": "tools/call",
                "params": {
                    "name": "wait_for_cancellation",
                    "arguments": {"private_input": "secret"},
                },
            },
            {"method": "notifications/cancelled", "params": {"requestId": "observed-actual-id"}},
        )
    ]
    async with load_script().RecordedSend(stream) as observer:
        for item in items:
            await observer.send(item)
        assert observer.request_ids == ["observed-actual-id"]
    assert stream.items == items
    assert all(a is b for a, b in zip(stream.items, items, strict=True))
    assert stream.closed


@pytest.mark.asyncio
async def test_controlled_fixture_records_cancellation_and_releases_sole_slot():
    fixture = load_script("mcp_cancellation_fixture")
    async with fixture.create_runtime() as runtime:
        assert runtime.max_concurrency == 1
        started = asyncio.Event()

        async def progress(_):
            started.set()

        call = asyncio.create_task(
            runtime.invoke(
                "wait_for_cancellation", {"private_input": "secret"}, progress_handler=progress
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 1)
            call.cancel()
            with pytest.raises(asyncio.CancelledError):
                await call
            inspected = await asyncio.wait_for(runtime.invoke("cancellation_state", {}), 1)
            assert inspected.output == {
                "active": 0,
                "cancelled": 1,
                "completed": 0,
                "runtime_cancelled": 1,
                "runtime_timed_out": 0,
                "in_flight": 1,
                "pending": 1,
            }
            assert runtime.metrics().in_flight == 0
            assert runtime.metrics().pending_invocations == 0
        finally:
            call.cancel()
            await asyncio.gather(call, return_exceptions=True)
