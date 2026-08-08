# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Protect a read-only vendor API tool with concurrency and sustained-rate limits."""

from __future__ import annotations

import asyncio
from typing import Literal, TypedDict

from samsarix_core import ToolRateLimit, ToolRuntime, ToolStatus, samsarix_tool


class VendorHealth(TypedDict):
    region: str
    status: str


@samsarix_tool(read_only=True, title="Get vendor health")
async def get_vendor_health(region: Literal["us", "eu"]) -> VendorHealth:
    """Return a stand-in for one application-owned vendor API response."""

    await asyncio.sleep(0)
    return {"region": region, "status": "available"}


async def main() -> None:
    async with ToolRuntime(max_concurrency=4) as runtime:
        runtime.register(
            get_vendor_health,
            max_concurrency=1,
            rate_limit=ToolRateLimit(calls=2, period_seconds=1, burst=1),
        )

        first = await runtime.invoke("get_vendor_health", {"region": "us"})
        limited = await runtime.invoke("get_vendor_health", {"region": "eu"})
        print(first.to_dict())
        print(limited.to_dict())

        if limited.status is not ToolStatus.RATE_LIMITED or limited.error is None:
            raise RuntimeError("Expected the second immediate call to be rate limited")
        details = limited.error.details
        retry_after_ms = details.get("retry_after_ms") if details is not None else None
        if isinstance(retry_after_ms, bool) or not isinstance(retry_after_ms, int):
            raise RuntimeError("Rate-limit result did not include a retry delay")

        await asyncio.sleep(retry_after_ms / 1_000 + 0.01)
        recovered = await runtime.invoke("get_vendor_health", {"region": "eu"})
        print(recovered.to_dict())
        if not recovered.success:
            raise RuntimeError("Tool did not recover after the reported retry delay")


if __name__ == "__main__":
    asyncio.run(main())
