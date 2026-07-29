# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded asynchronous invocation for registered local tools."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timezone
from functools import partial
from threading import Lock
from typing import Any, cast
from uuid import uuid4

from .errors import ToolArgumentError, ToolNotFoundError, ToolOutputError
from .models import JSONValue, RuntimeMetrics, ToolCall, ToolError, ToolResult, ToolSpec, ToolStatus
from .registry import RegisteredTool, ToolRegistry
from .schema import to_json_value, validate_arguments, validate_value


class ToolRuntime:
    """Invoke local tools with validation, timeouts, and bounded concurrency."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        max_concurrency: int = 8,
        default_timeout: float = 30.0,
        expose_exceptions: bool = False,
    ) -> None:
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
            raise TypeError("max_concurrency must be an integer")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        if (
            isinstance(default_timeout, bool)
            or not isinstance(default_timeout, (int, float))
            or default_timeout <= 0
        ):
            raise ValueError("default_timeout must be a positive number")

        self.registry = registry if registry is not None else ToolRegistry()
        self.max_concurrency = max_concurrency
        self.default_timeout = float(default_timeout)
        self.expose_exceptions = expose_exceptions
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="samsarix-tool"
        )
        self._active: set[asyncio.Task[JSONValue]] = set()
        self._closed = False
        self._metrics_lock = Lock()
        self._counters = {
            "calls_total": 0,
            "succeeded": 0,
            "not_found": 0,
            "invalid_arguments": 0,
            "timed_out": 0,
            "failed": 0,
            "runtime_closed": 0,
            "cancelled": 0,
            "in_flight": 0,
            "peak_in_flight": 0,
        }

    def register(self, function: Callable[..., Any], *, replace: bool = False) -> ToolSpec:
        """Register a decorated callable on this runtime."""

        return self.registry.register(function, replace=replace)

    async def invoke(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> ToolResult:
        """Attempt one invocation and return a structured terminal result."""

        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        invocation_id = uuid4().hex
        self._increment("calls_total")

        if self._closed:
            self._increment("runtime_closed")
            return self._result(
                invocation_id,
                name,
                ToolStatus.RUNTIME_CLOSED,
                started_at,
                started,
                error=ToolError("runtime_closed", "The tool runtime is closed"),
            )

        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            self._increment("invalid_arguments")
            return self._result(
                invocation_id,
                name,
                ToolStatus.INVALID_ARGUMENTS,
                started_at,
                started,
                error=ToolError("invalid_timeout", "Invocation timeout must be a positive number"),
            )

        try:
            registered = self.registry._resolve(name)
        except ToolNotFoundError:
            self._increment("not_found")
            return self._result(
                invocation_id,
                name,
                ToolStatus.NOT_FOUND,
                started_at,
                started,
                error=ToolError("tool_not_found", f"Tool '{name}' is not registered"),
            )

        try:
            supplied_arguments = arguments if arguments is not None else {}
            validated = validate_arguments(
                registered.signature, registered.hints, supplied_arguments
            )
        except ToolArgumentError as exc:
            self._increment("invalid_arguments")
            return self._result(
                invocation_id,
                name,
                ToolStatus.INVALID_ARGUMENTS,
                started_at,
                started,
                error=ToolError(
                    "invalid_arguments",
                    "Arguments do not match the tool contract",
                    details={"issues": cast(JSONValue, [issue.to_dict() for issue in exc.issues])},
                ),
            )

        effective_timeout = float(timeout or registered.spec.timeout or self.default_timeout)
        execution = asyncio.create_task(self._execute(registered, validated))
        self._active.add(execution)
        try:
            output = await asyncio.wait_for(execution, timeout=effective_timeout)
        except asyncio.TimeoutError:
            self._increment("timed_out")
            return self._result(
                invocation_id,
                name,
                ToolStatus.TIMED_OUT,
                started_at,
                started,
                error=ToolError(
                    "tool_timed_out",
                    f"Tool exceeded its {effective_timeout:g}-second timeout",
                ),
            )
        except asyncio.CancelledError:
            execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
            self._increment("cancelled")
            raise
        except ToolOutputError as exc:
            self._increment("failed")
            return self._result(
                invocation_id,
                name,
                ToolStatus.FAILED,
                started_at,
                started,
                error=ToolError(
                    "invalid_output",
                    "Tool returned a value that is not JSON-compatible",
                    type=type(exc).__name__,
                ),
            )
        except Exception as exc:
            self._increment("failed")
            message = str(exc) if self.expose_exceptions else "Tool execution failed"
            return self._result(
                invocation_id,
                name,
                ToolStatus.FAILED,
                started_at,
                started,
                error=ToolError("tool_failed", message, type=type(exc).__name__),
            )
        else:
            self._increment("succeeded")
            return self._result(
                invocation_id,
                name,
                ToolStatus.SUCCESS,
                started_at,
                started,
                output=output,
            )
        finally:
            self._active.discard(execution)

    async def invoke_many(self, calls: Sequence[ToolCall]) -> list[ToolResult]:
        """Invoke a batch in input order with a bounded number of worker tasks."""

        if not calls:
            return []
        results: list[ToolResult | None] = [None] * len(calls)
        pending = iter(enumerate(calls))

        async def worker() -> None:
            for index, call in pending:
                results[index] = await self.invoke(
                    call.name, dict(call.arguments), timeout=call.timeout
                )

        workers = [
            asyncio.create_task(worker()) for _ in range(min(self.max_concurrency, len(calls)))
        ]
        await asyncio.gather(*workers)
        return [cast(ToolResult, result) for result in results]

    def metrics(self) -> RuntimeMetrics:
        """Return content-free counters without tool names, arguments, or outputs."""

        with self._metrics_lock:
            return RuntimeMetrics(**self._counters)

    async def aclose(self) -> None:
        """Reject new calls, cancel active async waits, and release executor resources."""

        if self._closed:
            return
        self._closed = True
        active = tuple(self._active)
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        self._executor.shutdown(wait=False, cancel_futures=True)

    async def __aenter__(self) -> ToolRuntime:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    async def _execute(self, registered: RegisteredTool, arguments: dict[str, Any]) -> JSONValue:
        async with self._semaphore:
            self._begin_execution()
            try:
                if registered.spec.is_async:
                    awaitable = cast(Awaitable[Any], registered.function(**arguments))
                    raw_output = await awaitable
                else:
                    loop = asyncio.get_running_loop()
                    raw_output = await loop.run_in_executor(
                        self._executor, partial(registered.function, **arguments)
                    )
                if inspect.isawaitable(raw_output):
                    raise ToolOutputError("A synchronous tool returned an awaitable")
                try:
                    validated_output = validate_value(
                        raw_output, registered.hints["return"], path="$"
                    )
                    return to_json_value(validated_output)
                except ToolArgumentError as exc:
                    raise ToolOutputError("Tool output is not JSON-compatible") from exc
            finally:
                self._end_execution()

    def _begin_execution(self) -> None:
        with self._metrics_lock:
            self._counters["in_flight"] += 1
            self._counters["peak_in_flight"] = max(
                self._counters["peak_in_flight"], self._counters["in_flight"]
            )

    def _end_execution(self) -> None:
        with self._metrics_lock:
            self._counters["in_flight"] -= 1

    def _increment(self, name: str) -> None:
        with self._metrics_lock:
            self._counters[name] += 1

    @staticmethod
    def _result(
        invocation_id: str,
        tool_name: str,
        status: ToolStatus,
        started_at: str,
        started: float,
        *,
        output: JSONValue = None,
        error: ToolError | None = None,
    ) -> ToolResult:
        return ToolResult(
            invocation_id=invocation_id,
            tool_name=tool_name,
            status=status,
            started_at=started_at,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            output=output,
            error=error,
        )
