# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Immutable public data models for tool contracts and invocations."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, TypeAlias

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
TaskSupport: TypeAlias = Literal["forbidden", "optional", "required"]


class ToolStatus(str, Enum):
    """Terminal states returned by :class:`ToolRuntime`."""

    SUCCESS = "success"
    NOT_FOUND = "not_found"
    INVALID_ARGUMENTS = "invalid_arguments"
    DENIED = "denied"
    BUSY = "busy"
    TIMED_OUT = "timed_out"
    FAILED = "failed"
    RUNTIME_CLOSED = "runtime_closed"


@dataclass(frozen=True, slots=True)
class ToolError:
    """A safe error suitable for serialization across an application boundary."""

    code: str
    message: str
    type: str | None = None
    retryable: bool = False
    details: Mapping[str, JSONValue] | None = None

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a detached JSON-compatible representation."""

        data: dict[str, JSONValue] = {
            "code": self.code,
            "message": self.message,
            "retryable": self.retryable,
        }
        if self.type is not None:
            data["type"] = self.type
        if self.details is not None:
            data["details"] = deepcopy(dict(self.details))
        return data


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """The inspectable contract for one registered tool."""

    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    timeout: float | None
    version: str
    tags: tuple[str, ...]
    is_async: bool
    title: str | None = None
    read_only: bool = False
    destructive: bool = True
    idempotent: bool = False
    open_world: bool = True
    task_support: TaskSupport = "forbidden"

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a detached JSON-compatible representation."""

        return {
            "name": self.name,
            "description": self.description,
            "input_schema": deepcopy(self.input_schema),
            "output_schema": deepcopy(self.output_schema),
            "timeout": self.timeout,
            "version": self.version,
            "tags": list(self.tags),
            "is_async": self.is_async,
            "title": self.title,
            "read_only": self.read_only,
            "destructive": self.destructive,
            "idempotent": self.idempotent,
            "open_world": self.open_world,
            "task_support": self.task_support,
        }


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One item passed to :meth:`ToolRuntime.invoke_many`."""

    name: str
    arguments: Mapping[str, Any]
    timeout: float | None = None


class ToolPolicyDecision(str, Enum):
    """A host policy's explicit decision for one validated invocation."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ToolPolicyContext:
    """A detached validated call snapshot supplied only to host-owned policy code."""

    invocation_id: str
    spec: ToolSpec
    arguments: Mapping[str, Any]


ToolPolicy: TypeAlias = Callable[[ToolPolicyContext], Awaitable[ToolPolicyDecision]]


@dataclass(frozen=True, slots=True)
class ToolResult:
    """The structured result of one attempted tool invocation."""

    invocation_id: str
    tool_name: str
    status: ToolStatus
    started_at: str
    duration_ms: float
    output: JSONValue = None
    error: ToolError | None = None

    @property
    def success(self) -> bool:
        """Whether the invocation completed successfully."""

        return self.status is ToolStatus.SUCCESS

    def to_dict(self) -> dict[str, JSONValue]:
        """Return a detached JSON-compatible representation."""

        return {
            "invocation_id": self.invocation_id,
            "tool_name": self.tool_name,
            "status": self.status.value,
            "started_at": self.started_at,
            "duration_ms": self.duration_ms,
            "output": deepcopy(self.output),
            "error": self.error.to_dict() if self.error is not None else None,
        }


@dataclass(frozen=True, slots=True)
class RuntimeMetrics:
    """Content-free counters for runtime health checks."""

    calls_total: int
    succeeded: int
    not_found: int
    invalid_arguments: int
    denied: int
    timed_out: int
    failed: int
    runtime_closed: int
    cancelled: int
    in_flight: int
    peak_in_flight: int
    busy: int = 0
    pending_invocations: int = 0
    peak_pending_invocations: int = 0

    def to_dict(self) -> dict[str, int]:
        """Return the counters as a plain mapping."""

        return {
            "calls_total": self.calls_total,
            "succeeded": self.succeeded,
            "not_found": self.not_found,
            "invalid_arguments": self.invalid_arguments,
            "denied": self.denied,
            "busy": self.busy,
            "timed_out": self.timed_out,
            "failed": self.failed,
            "runtime_closed": self.runtime_closed,
            "cancelled": self.cancelled,
            "pending_invocations": self.pending_invocations,
            "peak_pending_invocations": self.peak_pending_invocations,
            "in_flight": self.in_flight,
            "peak_in_flight": self.peak_in_flight,
        }
