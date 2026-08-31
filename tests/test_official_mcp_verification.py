# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_mcp_client.py"


def load_script():
    spec = importlib.util.spec_from_file_location("official_mcp_verification", SCRIPT)
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
