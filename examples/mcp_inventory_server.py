# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run a small inventory tool server over the MCP stdio transport.

Launch this file as the command for a trusted local MCP client. The client sends
JSON-RPC on stdin and receives JSON-RPC on stdout; diagnostics belong on stderr.
"""

from __future__ import annotations

import asyncio

from samsarix_core import MCPServer, ToolRuntime, report_progress, samsarix_tool, serve_stdio


@samsarix_tool(
    title="Check inventory",
    tags=("inventory", "read"),
    read_only=True,
    open_world=False,
)
def check_inventory(sku: str) -> dict[str, int | str]:
    """Return available inventory from this example's local catalog."""

    catalog = {"cable-usb-c": 18, "keyboard-compact": 4}
    return {"sku": sku, "available": catalog.get(sku, 0)}


@samsarix_tool(
    title="Preview inventory reservation",
    tags=("inventory", "preview"),
    read_only=True,
    open_world=False,
)
def reserve_inventory(sku: str, quantity: int, request_id: str) -> dict[str, int | str]:
    """Return a deterministic reservation-shaped response for protocol demos."""

    return {"sku": sku, "quantity": quantity, "request_id": request_id, "status": "preview"}


@samsarix_tool(
    title="Audit inventory",
    tags=("inventory", "read", "progress"),
    read_only=True,
    open_world=False,
)
async def audit_inventory(skus: list[str]) -> dict[str, int]:
    """Count known inventory records while reporting completed work."""

    catalog = {"cable-usb-c": 18, "keyboard-compact": 4}
    known = 0
    for position, sku in enumerate(skus, start=1):
        known += int(sku in catalog)
        await report_progress(
            position,
            total=len(skus),
            message=f"Checked {position} of {len(skus)} inventory records",
        )
    return {"checked": len(skus), "known": known}


async def main() -> None:
    runtime = ToolRuntime(max_concurrency=4, default_timeout=10)
    runtime.register(check_inventory)
    runtime.register(reserve_inventory)
    runtime.register(audit_inventory)
    server = MCPServer(
        runtime,
        name="samsarix-inventory-example",
        title="Samsarix Inventory Example",
        instructions="Confirm with the user before calling tools that are not read-only.",
    )
    await serve_stdio(server)


if __name__ == "__main__":
    asyncio.run(main())
