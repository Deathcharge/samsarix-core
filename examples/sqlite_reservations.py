# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Demonstrate real, replay-safe inventory reservations in a temporary SQLite database."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path
from typing import Literal, TypedDict, cast

from samsarix_core import ToolPolicy, ToolRuntime, samsarix_tool

BUSY_TIMEOUT_SECONDS = 0.25
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
ReservationStatus = Literal[
    "reserved",
    "insufficient_stock",
    "unknown_sku",
    "idempotency_conflict",
    "invalid_request",
    "capacity_exceeded",
]


class ReservationResult(TypedDict):
    status: ReservationStatus
    available: int | None


class InventoryResult(TypedDict):
    available: int | None


def create_database(path: Path, *, stock: int = 5) -> None:
    """Initialize only a new host-selected file; never overwrite existing data."""

    if type(stock) is not int or not 0 <= stock <= 1_000_000:
        raise ValueError("stock must be an integer between 0 and 1000000")
    with path.open("xb"):
        pass
    with closing(sqlite3.connect(path, isolation_level=None)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "CREATE TABLE inventory (sku TEXT PRIMARY KEY NOT NULL, "
            "available INTEGER NOT NULL CHECK (available BETWEEN 0 AND 1000000))"
        )
        db.execute(
            "CREATE TABLE reservations (request_id TEXT PRIMARY KEY NOT NULL, "
            "sku TEXT NOT NULL, quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 1000), "
            "status TEXT NOT NULL CHECK (status IN "
            "('reserved', 'insufficient_stock', 'unknown_sku')), "
            "available INTEGER CHECK (available >= 0))"
        )
        db.execute("INSERT INTO inventory VALUES (?, ?)", ("cable-usb-c", stock))


class InventoryStore:
    """Application-owned storage, separate from Core's execution and policy layers."""

    def __init__(self, path: Path, *, max_requests: int = 1_000) -> None:
        if type(max_requests) is not int or not 1 <= max_requests <= 100_000:
            raise ValueError("max_requests must be an integer between 1 and 100000")
        self.path = path.resolve(strict=True)
        if not self.path.is_file():
            raise ValueError("database path must identify an existing file")
        self.max_requests = max_requests

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        # One connection per invocation stays on the worker thread that created it.
        # mode=rw prevents an accidentally removed store from being silently recreated.
        mode = "ro" if read_only else "rw"
        connection = sqlite3.connect(
            f"{self.path.as_uri()}?mode={mode}",
            uri=True,
            timeout=BUSY_TIMEOUT_SECONDS,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        return connection

    def check_inventory(self, sku: str) -> InventoryResult:
        if not isinstance(sku, str) or IDENTIFIER.fullmatch(sku) is None:
            raise ValueError("invalid SKU")
        with closing(self._connect(read_only=True)) as db:
            row = db.execute("SELECT available FROM inventory WHERE sku = ?", (sku,)).fetchone()
            return {"available": row["available"] if row is not None else None}

    def reserve(self, sku: str, quantity: int, request_id: str) -> ReservationResult:
        if (
            not isinstance(sku, str)
            or IDENTIFIER.fullmatch(sku) is None
            or not isinstance(request_id, str)
            or IDENTIFIER.fullmatch(request_id) is None
            or type(quantity) is not int
            or not 1 <= quantity <= 1_000
        ):
            return {"status": "invalid_request", "available": None}
        with closing(self._connect()) as db, db:
            # Serialize the complete read/check/write transaction, including replay
            # detection, across separate connections and runtime instances.
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute(
                "SELECT sku, quantity, status, available FROM reservations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            if previous is not None:
                if previous["sku"] != sku or previous["quantity"] != quantity:
                    return {"status": "idempotency_conflict", "available": None}
                return {
                    "status": cast(ReservationStatus, previous["status"]),
                    "available": previous["available"],
                }
            if db.execute("SELECT COUNT(*) FROM reservations").fetchone()[0] >= self.max_requests:
                return {"status": "capacity_exceeded", "available": None}
            row = db.execute("SELECT available FROM inventory WHERE sku = ?", (sku,)).fetchone()
            status: ReservationStatus = "unknown_sku"
            available = None
            if row is not None:
                available = int(row["available"])
                status = "insufficient_stock"
                if available >= quantity:
                    changed = db.execute(
                        "UPDATE inventory SET available = available - ? "
                        "WHERE sku = ? AND available >= ?",
                        (quantity, sku, quantity),
                    ).rowcount
                    if changed != 1:
                        raise RuntimeError("inventory update failed")
                    available -= quantity
                    status = "reserved"
            db.execute(
                "INSERT INTO reservations (request_id, sku, quantity, status, available) "
                "VALUES (?, ?, ?, ?, ?)",
                (request_id, sku, quantity, status, available),
            )
            # The connection context commits BEFORE this response reaches the caller.
            # Exceptions (including commit failure) roll back both writes together.
            return {"status": status, "available": available}


def create_runtime(store: InventoryStore, *, policy: ToolPolicy | None = None) -> ToolRuntime:
    """Bind a trusted store path outside the client-visible schema."""

    @samsarix_tool(read_only=True, open_world=False, tags=("inventory", "read"))
    def check_inventory(sku: str) -> InventoryResult:
        """Read current stock from the host-selected local database."""

        return store.check_inventory(sku)

    @samsarix_tool(idempotent=True, open_world=False, tags=("inventory", "write"))
    def reserve_inventory(sku: str, quantity: int, request_id: str) -> ReservationResult:
        """Reserve stock once per request ID; retry only with identical arguments."""

        return store.reserve(sku, quantity, request_id)

    runtime = ToolRuntime(
        max_concurrency=4,
        max_pending_invocations=32,
        max_batch_size=32,
        max_argument_bytes=4_096,
        max_output_bytes=4_096,
        default_timeout=2,
        policy=policy,
    )
    runtime.register(check_inventory)
    runtime.register(reserve_inventory, max_concurrency=1)
    return runtime


async def demonstrate(store: InventoryStore) -> dict[str, object]:
    """Execute, replay, reject a conflicting key, and replay after runtime restart."""

    arguments = {"sku": "cable-usb-c", "quantity": 2, "request_id": "order-001"}
    runtime = create_runtime(store)
    try:
        first = await runtime.invoke("reserve_inventory", arguments)
        replay = await runtime.invoke("reserve_inventory", arguments)
        conflict = await runtime.invoke("reserve_inventory", {**arguments, "quantity": 3})
    finally:
        if not await runtime.aclose(wait_for_sync=True, timeout=5):
            raise RuntimeError("reservation worker did not stop")
    restarted = create_runtime(store)
    try:
        after_restart = await restarted.invoke("reserve_inventory", arguments)
        stock = await restarted.invoke("check_inventory", {"sku": "cable-usb-c"})
    finally:
        if not await restarted.aclose(wait_for_sync=True, timeout=5):
            raise RuntimeError("reservation worker did not stop")
    expected = {"status": "reserved", "available": 3}
    if not (
        all(result.success for result in (first, replay, conflict, after_restart, stock))
        and first.output == replay.output == after_restart.output == expected
        and conflict.output == {"status": "idempotency_conflict", "available": None}
        and stock.output == {"available": 3}
    ):
        raise RuntimeError("transactional reservation verification failed")
    return {
        "first": first.output,
        "replay": replay.output,
        "conflict": conflict.output,
        "after_restart": after_restart.output,
        "current_stock": stock.output,
    }


def main() -> None:
    # Only this invocation's temporary database is created and later removed.
    with tempfile.TemporaryDirectory(prefix="samsarix-reservations-") as directory:
        path = Path(directory) / "inventory.sqlite3"
        create_database(path)
        report = asyncio.run(demonstrate(InventoryStore(path)))
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
