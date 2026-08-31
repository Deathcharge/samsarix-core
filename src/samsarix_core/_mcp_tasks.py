# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded in-memory state for experimental MCP task execution."""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from ._timeouts import normalize_timeout
from .models import JSONValue

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}


class TaskStoreError(Exception):
    """Base class for private task-store failures."""


class TaskNotFoundError(TaskStoreError):
    """Raised when a retained task does not exist or has expired."""


class TaskTerminalError(TaskStoreError):
    """Raised when cancellation targets a terminal task."""

    def __init__(self, status: str) -> None:
        super().__init__(status)
        self.status = status


class TaskCapacityError(TaskStoreError):
    """Raised when the bounded retained-task store is full."""


@dataclass(slots=True)
class RetainedTask:
    """One task state and its detached final MCP tool result."""

    task_id: str
    created_at: str
    last_updated_at: str
    created_monotonic: float
    ttl_ms: int
    poll_interval_ms: int
    status: str
    status_message: str
    done: asyncio.Event
    result: dict[str, JSONValue] | None = None
    execution: asyncio.Task[None] | None = None


class MCPTaskStore:
    """Retain a finite number of task results for a finite duration."""

    def __init__(
        self,
        *,
        max_tasks: int,
        default_ttl_ms: int,
        max_ttl_ms: int,
        poll_interval_ms: int,
    ) -> None:
        for name, value in (
            ("max_tasks", max_tasks),
            ("default_ttl_ms", default_ttl_ms),
            ("max_ttl_ms", max_ttl_ms),
            ("poll_interval_ms", poll_interval_ms),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
            if name != "max_tasks" and normalize_timeout(value) is None:
                raise ValueError(f"{name} must be representable as finite milliseconds")
        if default_ttl_ms > max_ttl_ms:
            raise ValueError("default_ttl_ms cannot exceed max_ttl_ms")

        self.max_tasks = max_tasks
        self.default_ttl_ms = default_ttl_ms
        self.max_ttl_ms = max_ttl_ms
        self.poll_interval_ms = poll_interval_ms
        self._tasks: dict[str, RetainedTask] = {}

    def create(
        self,
        operation: Callable[[str], Awaitable[dict[str, JSONValue]]],
        *,
        requested_ttl_ms: int | None,
    ) -> RetainedTask:
        """Accept one operation and immediately return its working task state."""

        self._purge_expired()
        if len(self._tasks) >= self.max_tasks:
            raise TaskCapacityError
        ttl_ms = min(requested_ttl_ms or self.default_ttl_ms, self.max_ttl_ms)
        now = _utc_now()
        retained = RetainedTask(
            task_id=uuid4().hex,
            created_at=now,
            last_updated_at=now,
            created_monotonic=time.monotonic(),
            ttl_ms=ttl_ms,
            poll_interval_ms=self.poll_interval_ms,
            status="working",
            status_message="Tool execution is in progress",
            done=asyncio.Event(),
        )
        self._tasks[retained.task_id] = retained
        retained.execution = asyncio.create_task(self._run(retained, operation))
        return retained

    def get(self, task_id: str) -> RetainedTask:
        """Return a live task or raise after bounded expiry cleanup."""

        self._purge_expired()
        try:
            return self._tasks[task_id]
        except KeyError as exc:
            raise TaskNotFoundError from exc

    async def result(self, task_id: str) -> dict[str, JSONValue]:
        """Wait for a terminal state, bounded by the task's remaining TTL."""

        retained = self.get(task_id)
        remaining = self._remaining_seconds(retained)
        if remaining <= 0:
            self._expire(retained)
            raise TaskNotFoundError
        try:
            await asyncio.wait_for(retained.done.wait(), timeout=remaining)
        except asyncio.TimeoutError as exc:
            self._expire(retained)
            raise TaskNotFoundError from exc
        if self._tasks.get(task_id) is not retained or retained.result is None:
            raise TaskNotFoundError
        return deepcopy(retained.result)

    def cancel(self, task_id: str) -> RetainedTask:
        """Make a working task terminal before requesting execution cancellation."""

        retained = self.get(task_id)
        if retained.status in _TERMINAL_STATUSES:
            raise TaskTerminalError(retained.status)
        retained.status = "cancelled"
        retained.status_message = "The task was cancelled by request"
        retained.last_updated_at = _utc_now()
        retained.result = _task_error_result(
            "task_cancelled",
            "Task execution was cancelled",
            task_id=retained.task_id,
        )
        retained.done.set()
        if retained.execution is not None:
            retained.execution.cancel()
        return retained

    async def aclose(self) -> None:
        """Cancel and join every retained background execution."""

        executions = tuple(
            retained.execution
            for retained in self._tasks.values()
            if retained.execution is not None and not retained.execution.done()
        )
        for execution in executions:
            execution.cancel()
        if executions:
            await asyncio.gather(*executions, return_exceptions=True)
        self._tasks.clear()

    @staticmethod
    def state(retained: RetainedTask) -> dict[str, JSONValue]:
        """Return the MCP Task shape without operation arguments or results."""

        return {
            "taskId": retained.task_id,
            "status": retained.status,
            "statusMessage": retained.status_message,
            "createdAt": retained.created_at,
            "lastUpdatedAt": retained.last_updated_at,
            "ttl": retained.ttl_ms,
            "pollInterval": retained.poll_interval_ms,
        }

    async def _run(
        self,
        retained: RetainedTask,
        operation: Callable[[str], Awaitable[dict[str, JSONValue]]],
    ) -> None:
        try:
            result = await operation(retained.task_id)
        except asyncio.CancelledError:
            if retained.status not in _TERMINAL_STATUSES:
                retained.status = "cancelled"
                retained.status_message = "Task execution was cancelled"
                retained.last_updated_at = _utc_now()
                retained.result = _task_error_result(
                    "task_cancelled",
                    "Task execution was cancelled",
                    task_id=retained.task_id,
                )
                retained.done.set()
            raise
        except Exception:
            result = _task_error_result(
                "task_execution_failed",
                "Task execution failed",
                task_id=retained.task_id,
            )

        if retained.status in _TERMINAL_STATUSES:
            return
        retained.result = deepcopy(result)
        retained.status = "failed" if result.get("isError") is True else "completed"
        retained.status_message = (
            "Tool execution failed" if retained.status == "failed" else "Tool execution completed"
        )
        retained.last_updated_at = _utc_now()
        retained.done.set()

    def _purge_expired(self) -> None:
        for retained in tuple(self._tasks.values()):
            if self._remaining_seconds(retained) <= 0:
                self._expire(retained)

    def _expire(self, retained: RetainedTask) -> None:
        if self._tasks.pop(retained.task_id, None) is retained:
            if retained.execution is not None and not retained.execution.done():
                retained.execution.cancel()
            retained.done.set()

    @staticmethod
    def _remaining_seconds(retained: RetainedTask) -> float:
        elapsed_ms = (time.monotonic() - retained.created_monotonic) * 1_000
        return max(0.0, (retained.ttl_ms - elapsed_ms) / 1_000)


def _task_error_result(code: str, message: str, *, task_id: str) -> dict[str, JSONValue]:
    payload = {"error": {"code": code, "message": message, "retryable": False}}
    return {
        "content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}],
        "isError": True,
        "_meta": {
            "io.modelcontextprotocol/related-task": {"taskId": task_id},
            "com.samsarix/status": "cancelled" if code == "task_cancelled" else "failed",
        },
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()
