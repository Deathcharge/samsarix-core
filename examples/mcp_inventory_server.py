# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Run a small inventory tool server over the MCP stdio transport.

Launch this file as the command for a trusted local MCP client. The client sends
JSON-RPC on stdin and receives JSON-RPC on stdout; diagnostics belong on stderr.
"""

from __future__ import annotations

import asyncio

from samsarix_core import MCPServer, ToolRuntime, samsarix_tool, serve_stdio


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
    title="Reserve inventory",
    tags=("inventory", "write"),
    destructive=False,
    idempotent=True,
    open_world=False,
)
def reserve_inventory(sku: str, quantity: int, request_id: str) -> dict[str, int | str]:
    """Demonstrate an idempotency-keyed inventory reservation."""

    return {"sku": sku, "quantity": quantity, "request_id": request_id, "status": "reserved"}


async def main() -> None:
    runtime = ToolRuntime(max_concurrency=4, default_timeout=10)
    runtime.register(check_inventory)
    runtime.register(reserve_inventory)
    server = MCPServer(
        runtime,
        name="samsarix-inventory-example",
        title="Samsarix Inventory Example",
        instructions="Confirm with the user before calling tools that are not read-only.",
    )
    await serve_stdio(server)


if __name__ == "__main__":
    asyncio.run(main())
