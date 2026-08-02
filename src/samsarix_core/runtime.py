# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded asynchronous invocation for registered local tools."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Awaitable, Callable, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from datetime import datetime, timezone
from functools import partial
from threading import Lock
from typing import Any, cast
from uuid import uuid4

from .errors import ProgressHandlerError, ToolArgumentError, ToolNotFoundError, ToolOutputError
from .models import JSONValue, RuntimeMetrics, ToolCall, ToolError, ToolResult, ToolSpec, ToolStatus
from .progress import (
    ProgressHandler,
    _close_progress,
    _open_progress,
    _ProgressScope,
    _stop_progress,
)
from .registry import RegisteredTool, ToolRegistry
from .schema import enforce_value_limits, to_json_value, validate_arguments, validate_value


class ToolRuntime:
    """Invoke local tools with validation, timeouts, and bounded concurrency."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        max_concurrency: int = 8,
        max_batch_size: int = 256,
        max_argument_bytes: int = 1_048_576,
        max_output_bytes: int = 1_048_576,
        max_value_depth: int = 32,
        max_value_nodes: int = 10_000,
        max_progress_updates: int = 1_000,
        max_progress_message_bytes: int = 4_096,
        default_timeout: float = 30.0,
        expose_exceptions: bool = False,
    ) -> None:
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
            raise TypeError("max_concurrency must be an integer")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        for name, value in (
            ("max_batch_size", max_batch_size),
            ("max_argument_bytes", max_argument_bytes),
            ("max_output_bytes", max_output_bytes),
            ("max_value_depth", max_value_depth),
            ("max_value_nodes", max_value_nodes),
            ("max_progress_updates", max_progress_updates),
            ("max_progress_message_bytes", max_progress_message_bytes),
        ):
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(f"{name} must be an integer")
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        if (
            isinstance(default_timeout, bool)
            or not isinstance(default_timeout, (int, float))
            or default_timeout <= 0
        ):
            raise ValueError("default_timeout must be a positive number")

        self.registry = registry if registry is not None else ToolRegistry()
        self.max_concurrency = max_concurrency
        self.max_batch_size = max_batch_size
        self.max_argument_bytes = max_argument_bytes
        self.max_output_bytes = max_output_bytes
        self.max_value_depth = max_value_depth
        self.max_value_nodes = max_value_nodes
        self.max_progress_updates = max_progress_updates
        self.max_progress_message_bytes = max_progress_message_bytes
        self.default_timeout = float(default_timeout)
        self.expose_exceptions = expose_exceptions
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._executor = ThreadPoolExecutor(
            max_workers=max_concurrency, thread_name_prefix="samsarix-tool"
        )
        self._active: set[asyncio.Task[JSONValue]] = set()
        self._active_progress: dict[asyncio.Task[JSONValue], _ProgressScope | None] = {}
        self._sync_futures: set[Future[Any]] = set()
        self._sync_futures_lock = Lock()
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
        progress_handler: ProgressHandler | None = None,
    ) -> ToolResult:
        """Attempt one invocation with optional progress and return its result."""

        started_at = datetime.now(timezone.utc).isoformat()
        started = time.perf_counter()
        invocation_id = uuid4().hex
        self._increment("calls_total")

        if progress_handler is not None and not callable(progress_handler):
            raise TypeError("progress_handler must be callable or None")

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
                error=ToolError("tool_not_found", "Tool is not registered"),
            )

        try:
            supplied_arguments = arguments if arguments is not None else {}
            enforce_value_limits(
                supplied_arguments,
                max_bytes=self.max_argument_bytes,
                max_depth=self.max_value_depth,
                max_nodes=self.max_value_nodes,
            )
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
        progress_scope, progress_token = _open_progress(
            progress_handler,
            max_updates=self.max_progress_updates,
            max_message_bytes=self.max_progress_message_bytes,
        )
        execution = asyncio.create_task(self._execute(registered, validated))
        self._active.add(execution)
        self._active_progress[execution] = progress_scope
        try:
            output = await asyncio.wait_for(
                asyncio.shield(execution),
                timeout=effective_timeout,
            )
        except asyncio.TimeoutError:
            _stop_progress(progress_scope)
            execution.cancel()
            with suppress(asyncio.CancelledError):
                await execution
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
            _stop_progress(progress_scope)
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
                    exc.code,
                    exc.public_message,
                    type=type(exc).__name__,
                ),
            )
        except ProgressHandlerError:
            raise
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
            self._active_progress.pop(execution, None)
            await _close_progress(progress_scope, progress_token)

    async def invoke_many(self, calls: Sequence[ToolCall]) -> list[ToolResult]:
        """Invoke a batch in input order with a bounded number of worker tasks."""

        if not calls:
            return []
        if len(calls) > self.max_batch_size:
            raise ValueError(f"Batch contains {len(calls)} calls; maximum is {self.max_batch_size}")
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

    @property
    def pending_sync_calls(self) -> int:
        """Return the number of submitted sync calls that have not actually stopped."""

        with self._sync_futures_lock:
            return len(self._sync_futures)

    async def wait_for_sync(self, *, timeout: float | None = None) -> bool:
        """Wait for currently submitted sync calls and report whether they stopped."""

        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0
        ):
            raise ValueError("timeout must be a non-negative number or None")
        with self._sync_futures_lock:
            pending = tuple(self._sync_futures)
        if not pending:
            return True

        waits = [self._wrap_sync_future(future) for future in pending]
        done, _ = await asyncio.wait(waits, timeout=timeout)
        return len(done) == len(waits)

    async def aclose(
        self,
        *,
        wait_for_sync: bool = False,
        timeout: float | None = None,
    ) -> bool:
        """Close the runtime and report whether its sync work is quiescent."""

        if not isinstance(wait_for_sync, bool):
            raise TypeError("wait_for_sync must be a boolean")
        if timeout is not None and not wait_for_sync:
            raise ValueError("timeout requires wait_for_sync=True")
        if (
            wait_for_sync
            and timeout is not None
            and (isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout < 0)
        ):
            raise ValueError("timeout must be a non-negative number or None")
        if not self._closed:
            self._closed = True
            active = tuple(self._active)
            for task in active:
                _stop_progress(self._active_progress.get(task))
                task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)
            self._executor.shutdown(wait=False, cancel_futures=True)
        if wait_for_sync:
            return await self.wait_for_sync(timeout=timeout)
        return self.pending_sync_calls == 0

    async def __aenter__(self) -> ToolRuntime:
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        await self.aclose()

    async def _execute(
        self,
        registered: RegisteredTool,
        arguments: dict[str, Any],
    ) -> JSONValue:
        if registered.spec.is_async:
            async with self._semaphore:
                self._begin_execution()
                try:
                    awaitable = cast(Awaitable[Any], registered.function(**arguments))
                    raw_output = await awaitable
                    return self._normalize_output(registered, raw_output)
                finally:
                    self._end_execution()

        await self._semaphore.acquire()
        loop = asyncio.get_running_loop()
        try:
            sync_future = self._executor.submit(self._run_sync, registered.function, arguments)
        except BaseException:
            self._semaphore.release()
            raise
        with self._sync_futures_lock:
            self._sync_futures.add(sync_future)
        sync_future.add_done_callback(partial(self._sync_finished, loop=loop))
        raw_output = await self._wrap_sync_future(sync_future)
        return self._normalize_output(registered, raw_output)

    def _run_sync(self, function: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        """Run one sync callable while tracking its real thread lifetime."""

        self._begin_execution()
        try:
            return function(**arguments)
        finally:
            self._end_execution()

    def _sync_finished(self, future: Future[Any], *, loop: asyncio.AbstractEventLoop) -> None:
        """Release one sync slot only after its underlying future is truly done."""

        with self._sync_futures_lock:
            self._sync_futures.discard(future)
        with suppress(RuntimeError):
            loop.call_soon_threadsafe(self._semaphore.release)

    @staticmethod
    def _wrap_sync_future(future: Future[Any]) -> asyncio.Future[Any]:
        """Wrap a thread future and consume late failures after caller timeout."""

        wrapped = asyncio.wrap_future(future)

        def consume_failure(completed: asyncio.Future[Any]) -> None:
            if not completed.cancelled():
                with suppress(BaseException):
                    completed.exception()

        wrapped.add_done_callback(consume_failure)
        return wrapped

    def _normalize_output(self, registered: RegisteredTool, raw_output: Any) -> JSONValue:
        """Validate and normalize one completed tool output."""

        if inspect.isawaitable(raw_output):
            raise ToolOutputError("A synchronous tool returned an awaitable")
        try:
            enforce_value_limits(
                raw_output,
                max_bytes=self.max_output_bytes,
                max_depth=self.max_value_depth,
                max_nodes=self.max_value_nodes,
            )
        except ToolArgumentError as exc:
            raise self._output_data_error(exc) from exc

        try:
            validated_output = validate_value(raw_output, registered.hints["return"], path="$")
        except ToolArgumentError as exc:
            raise ToolOutputError(
                "Tool output did not match its declared return type",
                public_message="Tool output did not match its declared return type",
            ) from exc

        try:
            normalized_output = to_json_value(validated_output)
            enforce_value_limits(
                normalized_output,
                max_bytes=self.max_output_bytes,
                max_depth=self.max_value_depth,
                max_nodes=self.max_value_nodes,
            )
            return normalized_output
        except ToolArgumentError as exc:
            raise self._output_data_error(exc) from exc

    @staticmethod
    def _output_data_error(error: ToolArgumentError) -> ToolOutputError:
        limit_codes = {"value_too_deep", "value_too_complex", "value_too_large"}
        exceeded_limit = any(issue.code in limit_codes for issue in error.issues)
        return ToolOutputError(
            "Tool output is not JSON-compatible",
            code="output_limit_exceeded" if exceeded_limit else "invalid_output",
            public_message=(
                "Tool output exceeded a configured resource limit"
                if exceeded_limit
                else "Tool returned a value that is not JSON-compatible"
            ),
        )

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
