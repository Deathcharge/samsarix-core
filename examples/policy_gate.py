# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Use a request-local capability in a fail-closed invocation policy."""

from __future__ import annotations

import asyncio
import json
from contextvars import ContextVar

from samsarix_core import (
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolRuntime,
    samsarix_tool,
)

_CURRENT_SCOPES: ContextVar[frozenset[str]] = ContextVar(
    "samsarix_example_scopes",
    default=frozenset(),
)


@samsarix_tool(
    title="Preview a policy-gated reservation",
    tags=("inventory", "write"),
    destructive=False,
    idempotent=True,
    open_world=False,
)
async def reserve_inventory(sku: str, quantity: int) -> dict[str, int | str]:
    """Simulate a policy-gated write without modifying inventory."""

    return {"sku": sku, "quantity": quantity, "status": "preview"}


async def require_inventory_write(context: ToolPolicyContext) -> ToolPolicyDecision:
    """Allow writes only when the current host context carries the required scope."""

    required_scope = "inventory:read" if context.spec.read_only else "inventory:write"
    return (
        ToolPolicyDecision.ALLOW
        if required_scope in _CURRENT_SCOPES.get()
        else ToolPolicyDecision.DENY
    )


async def main() -> None:
    async with ToolRuntime(policy=require_inventory_write) as runtime:
        runtime.register(reserve_inventory)
        arguments = {"sku": "keyboard-compact", "quantity": 1}

        denied = await runtime.invoke("reserve_inventory", arguments)

        token = _CURRENT_SCOPES.set(frozenset({"inventory:write"}))
        try:
            allowed = await runtime.invoke("reserve_inventory", arguments)
        finally:
            _CURRENT_SCOPES.reset(token)

        print(json.dumps({"denied": denied.to_dict(), "allowed": allowed.to_dict()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
