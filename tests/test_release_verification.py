# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

import samsarix_core

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


def test_sensitive_release_steps_require_push_and_tag():
    workflow = (SCRIPTS.parent / ".github/workflows/release.yml").read_text(encoding="utf-8")
    conditions = [line.strip() for line in workflow.splitlines() if line.strip().startswith("if:")]
    assert (
        conditions
        == ["if: github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"] * 4
    )


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_runtime_release_smoke_executes_the_public_contract():
    await load_script("smoke_check").verify_runtime()


@pytest.mark.asyncio
async def test_runtime_smoke_detects_wrong_output(monkeypatch):
    invoke = samsarix_core.ToolRuntime.invoke

    async def wrong_output(self, *args, **kwargs):
        result = await invoke(self, *args, **kwargs)
        return replace(result, output="wrong")

    monkeypatch.setattr(samsarix_core.ToolRuntime, "invoke", wrong_output)
    with pytest.raises(RuntimeError, match="Unicode echo failed"):
        await load_script("smoke_check").verify_runtime()


@pytest.mark.asyncio
async def test_runtime_smoke_detects_invalid_deadline_acceptance(monkeypatch):
    invoke = samsarix_core.ToolRuntime.invoke

    async def discard_timeout(self, *args, **kwargs):
        kwargs.pop("timeout", None)
        return await invoke(self, *args, **kwargs)

    monkeypatch.setattr(samsarix_core.ToolRuntime, "invoke", discard_timeout)
    with pytest.raises(RuntimeError, match="invalid deadline was not rejected"):
        await load_script("smoke_check").verify_runtime()


@pytest.mark.asyncio
async def test_runtime_smoke_detects_dropped_invalid_batch_items(monkeypatch):
    invoke_many = samsarix_core.ToolRuntime.invoke_many

    async def drop_invalid(self, calls):
        return await invoke_many(self, [call for call in calls if call.timeout is None])

    monkeypatch.setattr(samsarix_core.ToolRuntime, "invoke_many", drop_invalid)
    with pytest.raises(RuntimeError, match="invalid deadline disrupted a batch"):
        await load_script("smoke_check").verify_runtime()


@pytest.mark.asyncio
async def test_runtime_smoke_detects_unbounded_diagnostics(monkeypatch):
    invoke = samsarix_core.ToolRuntime.invoke

    async def oversized_diagnostics(self, name, *args, **kwargs):
        result = await invoke(self, name, *args, **kwargs)
        if name == "inspect_rows":
            issue = {"path": "$" + "x" * 256, "code": "type_mismatch", "message": "bad"}
            result = replace(result, error=replace(result.error, details={"issues": [issue]}))
        return result

    monkeypatch.setattr(samsarix_core.ToolRuntime, "invoke", oversized_diagnostics)
    with pytest.raises(RuntimeError, match="validation diagnostics are not bounded"):
        await load_script("smoke_check").verify_input_boundaries()


@pytest.mark.asyncio
async def test_runtime_smoke_detects_dropped_numeric_batch_items(monkeypatch):
    invoke_many = samsarix_core.ToolRuntime.invoke_many

    async def drop_bad_number(self, calls):
        return await invoke_many(self, calls[1:])

    monkeypatch.setattr(samsarix_core.ToolRuntime, "invoke_many", drop_bad_number)
    with pytest.raises(RuntimeError, match="numeric overflow disrupted a batch"):
        await load_script("smoke_check").verify_input_boundaries()


def test_release_smoke_detects_metadata_mismatch(monkeypatch):
    script = load_script("smoke_check")
    monkeypatch.setattr(script, "version", lambda name: "0.0.0")
    with pytest.raises(RuntimeError, match="distribution and import versions differ"):
        script.main()


def test_checks_are_not_disabled_by_python_optimization():
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-O",
            "-c",
            "import runpy; check = runpy.run_path("
            + repr(str(SCRIPTS / "smoke_check.py"))
            + ")['_require']; check(False, 'sentinel-failure')",
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode != 0
    assert b"sentinel-failure" in result.stderr


@pytest.mark.asyncio
async def test_real_mcp_subprocess_release_journey():
    await load_script("mcp_smoke_check").verify_server(
        SCRIPTS.parent / "examples" / "mcp_inventory_server.py"
    )


@pytest.mark.asyncio
async def test_mcp_smoke_rejects_non_protocol_stdout(tmp_path):
    child = tmp_path / "broken_server.py"
    child.write_text("print('debug chatter', flush=True)\n", encoding="utf-8")
    with pytest.raises(ValueError):
        await load_script("mcp_smoke_check").verify_server(child)


@pytest.mark.asyncio
async def test_mcp_smoke_kills_and_reaps_unresponsive_child(tmp_path, monkeypatch):
    child = tmp_path / "hung_server.py"
    child.write_text("import time\ntime.sleep(60)\n", encoding="utf-8")
    spawn = asyncio.create_subprocess_exec
    children = []

    async def record_child(*args, **kwargs):
        process = await spawn(*args, **kwargs)
        children.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", record_child)
    with pytest.raises(asyncio.TimeoutError):
        await load_script("mcp_smoke_check").verify_server(child, timeout=0.2)
    assert len(children) == 1
    assert children[0].returncode is not None


def test_distribution_check_requires_an_unambiguous_artifact(tmp_path):
    (tmp_path / "dist").mkdir()
    for name in ("first.whl", "second.whl"):
        (tmp_path / "dist" / name).touch()
    result = subprocess.run(
        [sys.executable, "-I", str(SCRIPTS / "verify_distribution.py")],
        cwd=tmp_path,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 2
    assert b"exactly one wheel" in result.stderr
