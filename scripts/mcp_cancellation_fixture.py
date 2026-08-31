# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Controlled, in-memory cancellation fixture; not an application or durable queue."""

from __future__ import annotations

import asyncio

from samsarix_core import MCPServer, ToolRuntime, report_progress, samsarix_tool, serve_stdio


def create_runtime() -> ToolRuntime:
    runtime = ToolRuntime(max_concurrency=1, max_pending_invocations=2, default_timeout=30)
    state = {"active": 0, "cancelled": 0, "completed": 0}

    @samsarix_tool(read_only=True, open_world=False)
    async def wait_for_cancellation(private_input: str) -> str:
        """Hold the sole execution slot until the client cancels this test call."""

        state["active"] += 1
        try:
            await report_progress(1, total=2, message="started")
            await asyncio.Event().wait()
            state["completed"] += 1
            return "unexpected completion"
        except asyncio.CancelledError:
            state["cancelled"] += 1
            raise
        finally:
            state["active"] -= 1

    @samsarix_tool(read_only=True, open_world=False)
    async def cancellation_state() -> dict[str, int]:
        """Return content-free cleanup counters while holding the recovered slot."""

        metrics = runtime.metrics()
        return {
            **state,
            "runtime_cancelled": metrics.cancelled,
            "runtime_timed_out": metrics.timed_out,
            "in_flight": metrics.in_flight,
            "pending": metrics.pending_invocations,
        }

    runtime.register(wait_for_cancellation)
    runtime.register(cancellation_state)
    return runtime


async def main() -> None:
    server = MCPServer(create_runtime(), name="samsarix-cancellation-fixture")
    await serve_stdio(server)


if __name__ == "__main__":
    asyncio.run(main())
