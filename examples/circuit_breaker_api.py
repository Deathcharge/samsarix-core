# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Fail fast around an unhealthy dependency, then prove one recovery probe."""

from __future__ import annotations

import asyncio
from typing import TypedDict

from samsarix_core import (
    ToolCircuitBreaker,
    ToolCircuitState,
    ToolRuntime,
    ToolStatus,
    samsarix_tool,
)


class VendorStatus(TypedDict):
    service: str
    available: bool


dependency_available = False


@samsarix_tool(read_only=True, title="Get vendor status")
async def get_vendor_status(service: str) -> VendorStatus:
    """Return a stand-in for one application-owned dependency request."""

    await asyncio.sleep(0)
    if not dependency_available:
        raise ConnectionError("vendor is unavailable")
    return {"service": service, "available": True}


async def main() -> None:
    global dependency_available

    async with ToolRuntime(max_concurrency=4) as runtime:
        runtime.register(
            get_vendor_status,
            max_concurrency=1,
            circuit_breaker=ToolCircuitBreaker(
                failure_threshold=1,
                recovery_timeout_seconds=0.05,
            ),
        )

        failed = await runtime.invoke("get_vendor_status", {"service": "catalog"})
        blocked = await runtime.invoke("get_vendor_status", {"service": "catalog"})
        print(failed.to_dict())
        print(blocked.to_dict())

        if failed.status is not ToolStatus.FAILED:
            raise RuntimeError("Expected the dependency call to fail")
        if blocked.status is not ToolStatus.CIRCUIT_OPEN or blocked.error is None:
            raise RuntimeError("Expected the open circuit to reject the next call")
        if runtime.circuit_state("get_vendor_status") is not ToolCircuitState.OPEN:
            raise RuntimeError("Expected an observable open circuit")

        details = blocked.error.details
        retry_after_ms = details.get("retry_after_ms") if details is not None else None
        if isinstance(retry_after_ms, bool) or not isinstance(retry_after_ms, int):
            raise RuntimeError("Open-circuit result did not include a retry delay")

        dependency_available = True
        await asyncio.sleep(retry_after_ms / 1_000 + 0.01)
        recovered = await runtime.invoke("get_vendor_status", {"service": "catalog"})
        print(recovered.to_dict())
        if not recovered.success:
            raise RuntimeError("Half-open recovery probe did not succeed")
        if runtime.circuit_state("get_vendor_status") is not ToolCircuitState.CLOSED:
            raise RuntimeError("Successful recovery probe did not close the circuit")


if __name__ == "__main__":
    asyncio.run(main())
