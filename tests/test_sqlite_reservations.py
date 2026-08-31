# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

from __future__ import annotations

import asyncio
import importlib.util
import json
import sqlite3
import subprocess
import sys
import threading
from contextlib import closing
from pathlib import Path

import pytest

from samsarix_core import ToolPolicyDecision, ToolStatus

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sqlite_reservations.py"
ARGUMENTS = {"sku": "cable-usb-c", "quantity": 2, "request_id": "order-001"}


@pytest.fixture(scope="module")
def example():
    spec = importlib.util.spec_from_file_location("_reservation_example", EXAMPLE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    yield module
    sys.modules.pop(spec.name)


@pytest.fixture
def store(example, tmp_path):
    path = tmp_path / "inventory space-東京.sqlite3"
    example.create_database(path)
    return example.InventoryStore(path)


def snapshot(store):
    with closing(sqlite3.connect(store.path)) as db:
        return (
            db.execute("SELECT available FROM inventory").fetchone()[0],
            db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0],
        )


async def test_reservation_demo_executes_and_replays_real_writes(example, store):
    report = await example.demonstrate(store)
    assert report["first"] == report["replay"] == report["after_restart"]
    assert report["first"] == {"status": "reserved", "available": 3}
    assert report["conflict"] == {"status": "idempotency_conflict", "available": None}
    assert snapshot(store) == (3, 1)


def test_initialization_never_overwrites_and_missing_store_is_not_recreated(example, store):
    with pytest.raises(FileExistsError):
        example.create_database(store.path)
    assert snapshot(store) == (5, 0)
    store.path.unlink()
    with pytest.raises(sqlite3.OperationalError):
        store.reserve(**ARGUMENTS)
    assert not store.path.exists()


@pytest.mark.parametrize("quantity", [0, -1, 1001, True, 1.5])
def test_store_rejects_invalid_quantities_without_writes(store, quantity):
    assert store.reserve(**{**ARGUMENTS, "quantity": quantity}) == {
        "status": "invalid_request",
        "available": None,
    }
    assert snapshot(store) == (5, 0)


@pytest.mark.parametrize("field", ["sku", "request_id"])
@pytest.mark.parametrize("value", ["", "x" * 65, "x'; DROP TABLE inventory; --", "../private"])
def test_identifiers_are_bounded_and_never_sql_fragments(store, field, value):
    result = store.reserve(**{**ARGUMENTS, field: value})
    assert result == {"status": "invalid_request", "available": None}
    assert snapshot(store) == (5, 0)


async def test_tool_validation_and_policy_denial_do_not_write(example, store):
    async def deny(context):
        return ToolPolicyDecision.DENY

    async with example.create_runtime(store, policy=deny) as runtime:
        invalid = await runtime.invoke("reserve_inventory", {**ARGUMENTS, "quantity": True})
        denied = await runtime.invoke("reserve_inventory", ARGUMENTS)
    assert invalid.status is ToolStatus.INVALID_ARGUMENTS
    assert denied.status is ToolStatus.DENIED
    assert snapshot(store) == (5, 0)
    store.reserve(**ARGUMENTS)
    async with example.create_runtime(store, policy=deny) as runtime:
        replay_denied = await runtime.invoke("reserve_inventory", ARGUMENTS)
    assert replay_denied.status is ToolStatus.DENIED
    assert snapshot(store) == (3, 1)


async def test_domain_rejections_are_recorded_and_replay_original_outcome(example, store):
    async with example.create_runtime(store) as runtime:
        insufficient = await runtime.invoke("reserve_inventory", {**ARGUMENTS, "quantity": 6})
        unknown = await runtime.invoke(
            "reserve_inventory", {**ARGUMENTS, "sku": "unknown", "request_id": "order-002"}
        )
        unknown_stock = await runtime.invoke("check_inventory", {"sku": "unknown"})
        # Simulate a later host-owned restock. An old key must keep its original outcome.
        with closing(sqlite3.connect(store.path)) as db, db:
            db.execute("UPDATE inventory SET available = 20")
        replay = await runtime.invoke("reserve_inventory", {**ARGUMENTS, "quantity": 6})
    assert insufficient.success and unknown.success and replay.success
    assert insufficient.output == replay.output == {"status": "insufficient_stock", "available": 5}
    assert unknown.output == {"status": "unknown_sku", "available": None}
    assert unknown_stock.success and unknown_stock.output == {"available": None}
    assert snapshot(store) == (20, 2)


async def test_separate_runtime_connections_cannot_duplicate_or_oversell(example, store):
    other_store = example.InventoryStore(store.path)
    async with (
        example.create_runtime(store) as first,
        example.create_runtime(other_store) as second,
    ):
        duplicates = await asyncio.gather(
            first.invoke("reserve_inventory", ARGUMENTS),
            second.invoke("reserve_inventory", ARGUMENTS),
        )
        assert all(result.success for result in duplicates)
        assert (
            duplicates[0].output == duplicates[1].output == {"status": "reserved", "available": 3}
        )
        competitors = await asyncio.gather(
            first.invoke("reserve_inventory", {**ARGUMENTS, "request_id": "order-002"}),
            second.invoke("reserve_inventory", {**ARGUMENTS, "request_id": "order-003"}),
        )
    assert all(result.success for result in competitors)
    assert sorted(result.output["status"] for result in competitors) == [
        "insufficient_stock",
        "reserved",
    ]
    assert snapshot(store) == (1, 3)


async def test_ledger_insert_failure_rolls_back_stock_and_redacts_error(example, store):
    with closing(sqlite3.connect(store.path)) as db, db:
        db.execute(
            "CREATE TRIGGER fail_ledger BEFORE INSERT ON reservations "
            "BEGIN SELECT RAISE(ABORT, 'private-storage-error'); END"
        )
    async with example.create_runtime(store) as runtime:
        result = await runtime.invoke("reserve_inventory", ARGUMENTS)
    assert result.status is ToolStatus.FAILED
    assert "private-storage-error" not in json.dumps(result.to_dict())
    assert str(store.path) not in json.dumps(result.to_dict())
    assert snapshot(store) == (5, 0)


async def test_database_lock_fails_safely_without_waiting_forever(example, store, monkeypatch):
    monkeypatch.setattr(example, "BUSY_TIMEOUT_SECONDS", 0.02)
    with closing(sqlite3.connect(store.path)) as owner:
        owner.execute("BEGIN IMMEDIATE")
        async with example.create_runtime(store) as runtime:
            result = await asyncio.wait_for(runtime.invoke("reserve_inventory", ARGUMENTS), 5)
        owner.rollback()
    assert result.status is ToolStatus.FAILED
    assert result.error.code == "tool_failed"
    assert snapshot(store) == (5, 0)


async def test_commit_failure_rolls_back_stock_and_ledger(example, store, monkeypatch):
    monkeypatch.setattr(example, "BUSY_TIMEOUT_SECONDS", 0.02)
    with closing(sqlite3.connect(store.path)) as reader:
        reader.execute("BEGIN")
        reader.execute("SELECT * FROM inventory").fetchall()
        # A rollback-journal reader allows BEGIN IMMEDIATE and the writes, but
        # prevents the writer obtaining the exclusive lock needed by COMMIT.
        async with example.create_runtime(store) as runtime:
            result = await asyncio.wait_for(runtime.invoke("reserve_inventory", ARGUMENTS), 5)
        reader.rollback()
    assert result.status is ToolStatus.FAILED
    assert snapshot(store) == (5, 0)


@pytest.mark.parametrize("value", [0, -1, 100001, True, 1.5])
def test_store_capacity_is_bounded(example, store, value):
    with pytest.raises(ValueError, match="max_requests"):
        example.InventoryStore(store.path, max_requests=value)


def test_database_configuration_fails_before_touching_files(example, tmp_path):
    with pytest.raises(ValueError, match="existing file"):
        example.InventoryStore(tmp_path)
    target = tmp_path / "not-created.sqlite3"
    with pytest.raises(ValueError, match="stock"):
        example.create_database(target, stock=True)
    assert not target.exists()


@pytest.mark.parametrize("stop", ["timeout", "cancel"])
async def test_replay_after_commit_but_before_response_never_writes_twice(
    example, store, monkeypatch, stop
):
    committed = threading.Event()
    release = threading.Event()
    reserve = store.reserve

    def delayed_response(*args, **kwargs):
        result = reserve(*args, **kwargs)
        committed.set()
        if not release.wait(5):
            raise RuntimeError("test did not release committed worker")
        return result

    monkeypatch.setattr(store, "reserve", delayed_response)
    runtime = example.create_runtime(store)
    try:
        task = asyncio.create_task(
            runtime.invoke("reserve_inventory", ARGUMENTS, timeout=0.05 if stop == "timeout" else 5)
        )
        assert await asyncio.to_thread(committed.wait, 5)
        if stop == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            assert (await task).status is ToolStatus.TIMED_OUT
        assert runtime.metrics().in_flight == 1
        assert not await runtime.aclose(wait_for_sync=True, timeout=0.01)
        assert snapshot(store) == (3, 1)
    finally:
        release.set()
        assert await runtime.aclose(wait_for_sync=True, timeout=5)
    async with example.create_runtime(example.InventoryStore(store.path)) as restarted:
        replay = await restarted.invoke("reserve_inventory", ARGUMENTS)
    assert replay.success and replay.output == {"status": "reserved", "available": 3}
    assert snapshot(store) == (3, 1)


async def test_request_capacity_never_evicts_saved_replays(example, store):
    bounded = example.InventoryStore(store.path, max_requests=1)
    async with example.create_runtime(bounded) as runtime:
        first = await runtime.invoke("reserve_inventory", ARGUMENTS)
        rejected = await runtime.invoke(
            "reserve_inventory", {**ARGUMENTS, "request_id": "order-002"}
        )
        replay = await runtime.invoke("reserve_inventory", ARGUMENTS)
    assert first.output == replay.output == {"status": "reserved", "available": 3}
    assert rejected.output == {"status": "capacity_exceeded", "available": None}
    assert snapshot(store) == (3, 1)


def test_process_restart_replays_committed_database(example, store):
    assert store.reserve(**ARGUMENTS) == {"status": "reserved", "available": 3}
    code = f"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, {str(EXAMPLE.parent)!r})
from sqlite_reservations import InventoryStore, create_runtime
async def main():
    async with create_runtime(InventoryStore(Path({str(store.path)!r}))) as runtime:
        result = await runtime.invoke('reserve_inventory', {ARGUMENTS!r})
        if not result.success:
            raise RuntimeError('child invocation failed')
        print(json.dumps(result.output))
asyncio.run(main())
"""
    child = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=15)
    assert child.returncode == 0, child.stderr
    assert json.loads(child.stdout) == {"status": "reserved", "available": 3}
    assert snapshot(store) == (3, 1)


def test_contract_marks_real_write_and_hides_host_path(example, store):
    runtime = example.create_runtime(store)
    try:
        spec = runtime.registry.get("reserve_inventory")
        assert not spec.read_only and spec.destructive and spec.idempotent and not spec.open_world
        assert set(spec.input_schema["properties"]) == {"sku", "quantity", "request_id"}
        assert str(store.path) not in json.dumps(spec.to_dict())
    finally:
        asyncio.run(runtime.aclose())
