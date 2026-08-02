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
from copy import deepcopy
from datetime import datetime, timezone
from functools import partial
from threading import Lock
from typing import Any, cast
from uuid import uuid4

from .errors import ProgressHandlerError, ToolArgumentError, ToolNotFoundError, ToolOutputError
from .models import (
    JSONValue,
    RuntimeMetrics,
    ToolCall,
    ToolError,
    ToolLifecycleEvent,
    ToolLifecycleHandler,
    ToolLifecycleStatus,
    ToolPolicy,
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolResult,
    ToolSpec,
    ToolStatus,
)
from .progress import (
    ProgressHandler,
    _close_progress,
    _open_progress,
    _ProgressScope,
    _stop_progress,
)
from .registry import RegisteredTool, ToolRegistry
from .schema import enforce_value_limits, to_json_value, validate_arguments, validate_value


class _ToolPolicyDenied(Exception):
    """Signal an explicit policy denial inside one invocation task."""


class _ToolPolicyFailed(Exception):
    """Signal that a host policy failed closed."""


def _is_async_callable(value: object) -> bool:
    """Recognize async functions and objects with an async ``__call__``."""

    return inspect.iscoroutinefunction(value) or (
        callable(value) and inspect.iscoroutinefunction(type(value).__call__)
    )


class ToolRuntime:
    """Invoke local tools with validation, timeouts, and bounded concurrency."""

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        *,
        max_concurrency: int = 8,
        max_pending_invocations: int = 256,
        max_batch_size: int = 256,
        max_argument_bytes: int = 1_048_576,
        max_output_bytes: int = 1_048_576,
        max_value_depth: int = 32,
        max_value_nodes: int = 10_000,
        max_progress_updates: int = 1_000,
        max_progress_message_bytes: int = 4_096,
        default_timeout: float = 30.0,
        expose_exceptions: bool = False,
        policy: ToolPolicy | None = None,
        lifecycle_handler: ToolLifecycleHandler | None = None,
    ) -> None:
        if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
            raise TypeError("max_concurrency must be an integer")
        if max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive")
        for name, value in (
            ("max_pending_invocations", max_pending_invocations),
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
        if policy is not None and not _is_async_callable(policy):
            raise TypeError("policy must be an async callable or None")
        if lifecycle_handler is not None and (
            not callable(lifecycle_handler) or _is_async_callable(lifecycle_handler)
        ):
            raise TypeError("lifecycle_handler must be a synchronous callable or None")

        self.registry = registry if registry is not None else ToolRegistry()
        self.max_concurrency = max_concurrency
        self.max_pending_invocations = max_pending_invocations
        self.max_batch_size = max_batch_size
        self.max_argument_bytes = max_argument_bytes
        self.max_output_bytes = max_output_bytes
        self.max_value_depth = max_value_depth
        self.max_value_nodes = max_value_nodes
        self.max_progress_updates = max_progress_updates
        self.max_progress_message_bytes = max_progress_message_bytes
        self.default_timeout = float(default_timeout)
        self.expose_exceptions = expose_exceptions
        self.policy = policy
        self.lifecycle_handler = lifecycle_handler
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._policy_semaphore = asyncio.Semaphore(max_concurrency)
        self._tool_semaphores: dict[int, tuple[RegisteredTool, asyncio.Semaphore]] = {}
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
            "denied": 0,
            "busy": 0,
            "timed_out": 0,
            "failed": 0,
            "runtime_closed": 0,
            "cancelled": 0,
            "pending_invocations": 0,
            "peak_pending_invocations": 0,
            "in_flight": 0,
            "peak_in_flight": 0,
            "lifecycle_handler_failures": 0,
        }

    def register(
        self,
        function: Callable[..., Any],
        *,
        replace: bool = False,
        max_concurrency: int | None = None,
    ) -> ToolSpec:
        """Register a decorated callable with an optional execution bulkhead."""

        if max_concurrency is not None:
            if isinstance(max_concurrency, bool) or not isinstance(max_concurrency, int):
                raise TypeError("max_concurrency must be an integer or None")
            if max_concurrency <= 0:
                raise ValueError("max_concurrency must be positive")

        # Keep the callable registration and its deployment-local policy atomic
        # with respect to both direct registry mutation and invocation resolution.
        with self.registry._lock:
            spec = self.registry.register(function, replace=replace)
            registered = self.registry._resolve(spec.name)
            tool_semaphores = {
                key: entry
                for key, entry in self._tool_semaphores.items()
                if entry[0].spec.name != spec.name
            }
            if max_concurrency is not None:
                tool_semaphores[id(registered)] = (
                    registered,
                    asyncio.Semaphore(max_concurrency),
                )
            self._tool_semaphores = tool_semaphores
        return spec

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
        self._emit_lifecycle(
            invocation_id,
            name,
            ToolLifecycleStatus.STARTED,
            occurred_at=started_at,
        )
        try:
            if progress_handler is not None and not callable(progress_handler):
                raise TypeError("progress_handler must be callable or None")

            if self._closed:
                self._increment("runtime_closed")
                result = self._result(
                    invocation_id,
                    name,
                    ToolStatus.RUNTIME_CLOSED,
                    started_at,
                    started,
                    error=ToolError("runtime_closed", "The tool runtime is closed"),
                )
            elif timeout is not None and (
                isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
            ):
                self._increment("invalid_arguments")
                result = self._result(
                    invocation_id,
                    name,
                    ToolStatus.INVALID_ARGUMENTS,
                    started_at,
                    started,
                    error=ToolError(
                        "invalid_timeout", "Invocation timeout must be a positive number"
                    ),
                )
            elif not self._try_admit():
                self._increment("busy")
                result = self._result(
                    invocation_id,
                    name,
                    ToolStatus.BUSY,
                    started_at,
                    started,
                    error=ToolError(
                        "runtime_busy",
                        "Runtime invocation capacity is full",
                        retryable=True,
                    ),
                )
            else:
                try:
                    result = await self._invoke_admitted(
                        name,
                        arguments,
                        timeout=timeout,
                        progress_handler=progress_handler,
                        invocation_id=invocation_id,
                        started_at=started_at,
                        started=started,
                    )
                finally:
                    self._release_admission()
        except asyncio.CancelledError:
            self._emit_lifecycle(
                invocation_id,
                name,
                ToolLifecycleStatus.CANCELLED,
                duration_ms=self._duration_ms(started),
            )
            raise
        except Exception:
            self._emit_lifecycle(
                invocation_id,
                name,
                ToolLifecycleStatus.ABORTED,
                duration_ms=self._duration_ms(started),
            )
            raise

        try:
            lifecycle_status = ToolLifecycleStatus(result.status.value)
        except ValueError:
            # A future result status must not discard an already-computed result if
            # lifecycle models have not yet been updated to match it.
            self._increment("lifecycle_handler_failures")
        else:
            self._emit_lifecycle(
                invocation_id,
                name,
                lifecycle_status,
                duration_ms=result.duration_ms,
            )
        return result

    async def _invoke_admitted(
        self,
        name: str,
        arguments: dict[str, Any] | None,
        *,
        timeout: float | None,
        progress_handler: ProgressHandler | None,
        invocation_id: str,
        started_at: str,
        started: float,
    ) -> ToolResult:
        """Resolve, validate, authorize, and execute one admitted invocation."""

        try:
            with self.registry._lock:
                registered = self.registry._resolve(name)
                tool_bulkhead = self._tool_semaphores.get(id(registered))
                tool_semaphore = (
                    tool_bulkhead[1]
                    if tool_bulkhead is not None and tool_bulkhead[0] is registered
                    else None
                )
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
        execution = asyncio.create_task(
            self._authorize_and_execute(
                registered,
                validated,
                invocation_id=invocation_id,
                tool_semaphore=tool_semaphore,
            )
        )
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
        except _ToolPolicyDenied:
            self._increment("denied")
            return self._result(
                invocation_id,
                name,
                ToolStatus.DENIED,
                started_at,
                started,
                error=ToolError(
                    "tool_denied",
                    "Tool invocation was denied by host policy",
                ),
            )
        except _ToolPolicyFailed:
            self._increment("failed")
            return self._result(
                invocation_id,
                name,
                ToolStatus.FAILED,
                started_at,
                started,
                error=ToolError(
                    "tool_policy_failed",
                    "Tool invocation policy failed",
                ),
            )
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
        """Invoke a batch in input order with pending-capacity-bounded workers."""

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

        # Execution remains globally and per-tool bounded inside ``invoke``. Using
        # pending capacity here prevents workers waiting on one tool's bulkhead
        # from head-of-line blocking unrelated calls later in a mixed batch.
        worker_count = min(self.max_pending_invocations, len(calls))
        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
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
        tool_semaphore: asyncio.Semaphore | None,
    ) -> JSONValue:
        if registered.spec.is_async:
            if tool_semaphore is not None:
                await tool_semaphore.acquire()
            try:
                async with self._semaphore:
                    self._begin_execution()
                    try:
                        awaitable = cast(Awaitable[Any], registered.function(**arguments))
                        raw_output = await awaitable
                        return self._normalize_output(registered, raw_output)
                    finally:
                        self._end_execution()
            finally:
                if tool_semaphore is not None:
                    tool_semaphore.release()

        if tool_semaphore is not None:
            await tool_semaphore.acquire()
        try:
            await self._semaphore.acquire()
        except BaseException:
            if tool_semaphore is not None:
                tool_semaphore.release()
            raise
        loop = asyncio.get_running_loop()
        try:
            sync_future = self._executor.submit(self._run_sync, registered.function, arguments)
        except BaseException:
            self._semaphore.release()
            if tool_semaphore is not None:
                tool_semaphore.release()
            raise
        with self._sync_futures_lock:
            self._sync_futures.add(sync_future)
        sync_future.add_done_callback(
            partial(
                self._sync_finished,
                loop=loop,
                tool_semaphore=tool_semaphore,
            )
        )
        raw_output = await self._wrap_sync_future(sync_future)
        return self._normalize_output(registered, raw_output)

    async def _authorize_and_execute(
        self,
        registered: RegisteredTool,
        arguments: dict[str, Any],
        *,
        invocation_id: str,
        tool_semaphore: asyncio.Semaphore | None,
    ) -> JSONValue:
        """Fail closed on one bounded policy decision before tool execution."""

        if self.policy is not None:
            context = ToolPolicyContext(
                invocation_id=invocation_id,
                spec=deepcopy(registered.spec),
                arguments=deepcopy(arguments),
            )
            async with self._policy_semaphore:
                try:
                    decision = await self.policy(context)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    raise _ToolPolicyFailed from exc
            if not isinstance(decision, ToolPolicyDecision):
                raise _ToolPolicyFailed
            if decision is ToolPolicyDecision.DENY:
                raise _ToolPolicyDenied
        return await self._execute(registered, arguments, tool_semaphore)

    def _run_sync(self, function: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        """Run one sync callable while tracking its real thread lifetime."""

        self._begin_execution()
        try:
            return function(**arguments)
        finally:
            self._end_execution()

    def _sync_finished(
        self,
        future: Future[Any],
        *,
        loop: asyncio.AbstractEventLoop,
        tool_semaphore: asyncio.Semaphore | None,
    ) -> None:
        """Release global and tool slots after the sync future is truly done."""

        with self._sync_futures_lock:
            self._sync_futures.discard(future)

        def release_slots() -> None:
            self._semaphore.release()
            if tool_semaphore is not None:
                tool_semaphore.release()

        with suppress(RuntimeError):
            loop.call_soon_threadsafe(release_slots)

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

    def _try_admit(self) -> bool:
        """Atomically reserve one non-terminal invocation slot without waiting."""

        with self._metrics_lock:
            if self._counters["pending_invocations"] >= self.max_pending_invocations:
                return False
            self._counters["pending_invocations"] += 1
            self._counters["peak_pending_invocations"] = max(
                self._counters["peak_pending_invocations"],
                self._counters["pending_invocations"],
            )
            return True

    def _release_admission(self) -> None:
        """Release one invocation slot on every terminal or cancellation path."""

        with self._metrics_lock:
            self._counters["pending_invocations"] -= 1

    def _increment(self, name: str) -> None:
        with self._metrics_lock:
            self._counters[name] += 1

    def _emit_lifecycle(
        self,
        invocation_id: str,
        tool_name: str,
        status: ToolLifecycleStatus,
        *,
        occurred_at: str | None = None,
        duration_ms: float | None = None,
    ) -> None:
        """Deliver one best-effort content-free lifecycle event inline."""

        if self.lifecycle_handler is None:
            return
        event = ToolLifecycleEvent(
            invocation_id=invocation_id,
            tool_name=tool_name,
            status=status,
            occurred_at=occurred_at or datetime.now(timezone.utc).isoformat(),
            duration_ms=duration_ms,
        )
        try:
            returned = self.lifecycle_handler(event)
            if inspect.isawaitable(returned):
                self._dispose_lifecycle_awaitable(returned)
                raise TypeError("lifecycle_handler returned an awaitable")
        except Exception:
            self._increment("lifecycle_handler_failures")

    @staticmethod
    def _dispose_lifecycle_awaitable(returned: object) -> None:
        """Best-effort cleanup without awaiting or scheduling handler output."""

        if isinstance(returned, asyncio.Future):
            if returned.done():
                ToolRuntime._consume_lifecycle_future(returned)
            else:
                returned.add_done_callback(ToolRuntime._consume_lifecycle_future)
                returned.cancel()
            return

        for method_name in ("cancel", "close"):
            cleanup = getattr(returned, method_name, None)
            if callable(cleanup):
                cleanup()
                return

    @staticmethod
    def _consume_lifecycle_future(completed: asyncio.Future[Any]) -> None:
        """Retrieve a completed handler Future failure to avoid late warnings."""

        if not completed.cancelled():
            with suppress(BaseException):
                completed.exception()

    @staticmethod
    def _duration_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)

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
            duration_ms=ToolRuntime._duration_ms(started),
            output=output,
            error=error,
        )
