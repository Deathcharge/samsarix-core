# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Bounded, invocation-scoped progress reporting for asynchronous tools."""

from __future__ import annotations

import asyncio
import inspect
import math
from collections.abc import Awaitable, Callable
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import TypeAlias

from .errors import ProgressHandlerError


@dataclass(frozen=True, slots=True)
class ToolProgress:
    """One structured progress update emitted by a running tool."""

    progress: float
    total: float | None = None
    message: str | None = None


ProgressHandler: TypeAlias = Callable[[ToolProgress], Awaitable[None] | None]


class _ProgressScope:
    """Serialize and bound progress updates for one invocation."""

    def __init__(
        self,
        handler: ProgressHandler,
        *,
        max_updates: int,
        max_message_bytes: int,
    ) -> None:
        self.handler = handler
        self.max_updates = max_updates
        self.max_message_bytes = max_message_bytes
        self._lock = asyncio.Lock()
        self._last_progress: float | None = None
        self._updates = 0
        self._closed = False

    async def report(self, update: ToolProgress) -> bool:
        """Deliver one valid update or report that the configured cap was reached."""

        async with self._lock:
            if self._closed:
                return False
            if self._last_progress is not None and update.progress <= self._last_progress:
                raise ValueError("progress must increase with every reported update")
            self._last_progress = update.progress
            if self._updates >= self.max_updates:
                return False

            handler_token = _ACTIVE_PROGRESS.set(None)
            try:
                outcome = self.handler(update)
                if inspect.isawaitable(outcome):
                    await outcome
            except ProgressHandlerError:
                raise
            except Exception as exc:
                raise ProgressHandlerError("Progress handler failed") from exc
            finally:
                _ACTIVE_PROGRESS.reset(handler_token)
            self._updates += 1
            return True

    async def close(self) -> None:
        """Stop future updates and wait for an update already being delivered."""

        self.stop()
        async with self._lock:
            return

    def stop(self) -> None:
        """Synchronously prevent new updates before task cancellation."""

        self._closed = True


_ACTIVE_PROGRESS: ContextVar[_ProgressScope | None] = ContextVar(
    "samsarix_active_progress", default=None
)


def _open_progress(
    handler: ProgressHandler | None,
    *,
    max_updates: int,
    max_message_bytes: int,
) -> tuple[_ProgressScope | None, Token[_ProgressScope | None]]:
    scope = (
        _ProgressScope(
            handler,
            max_updates=max_updates,
            max_message_bytes=max_message_bytes,
        )
        if handler is not None
        else None
    )
    return scope, _ACTIVE_PROGRESS.set(scope)


async def _close_progress(
    scope: _ProgressScope | None,
    token: Token[_ProgressScope | None],
) -> None:
    try:
        if scope is not None:
            await scope.close()
    finally:
        _ACTIVE_PROGRESS.reset(token)


def _stop_progress(scope: _ProgressScope | None) -> None:
    if scope is not None:
        scope.stop()


async def report_progress(
    progress: int | float,
    *,
    total: int | float | None = None,
    message: str | None = None,
) -> bool:
    """Report progress for the current async invocation when a handler is present.

    The return value is ``True`` when the active handler accepted the update. It
    is ``False`` when the caller did not request progress, the invocation has
    completed, or the configured per-invocation update cap has been reached.
    """

    progress_value = _finite_non_negative_number(progress, name="progress")
    total_value = _finite_non_negative_number(total, name="total") if total is not None else None
    if message is not None and not isinstance(message, str):
        raise TypeError("message must be a string or None")

    scope = _ACTIVE_PROGRESS.get()
    if scope is None:
        return False
    if message is not None and len(message.encode("utf-8")) > scope.max_message_bytes:
        raise ValueError(f"progress message exceeds the {scope.max_message_bytes}-byte limit")
    return await scope.report(ToolProgress(progress_value, total_value, message))


def _finite_non_negative_number(value: object, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a number")
    try:
        normalized = float(value)
    except OverflowError as exc:
        raise ValueError(f"{name} must be finite and non-negative") from exc
    if not math.isfinite(normalized) or normalized < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return normalized
