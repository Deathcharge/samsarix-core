# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Samsarix Core: typed local Python tools with bounded async invocation."""

from ._version import __version__
from .decorators import helix_tool, samsarix_tool
from .errors import (
    DuplicateToolError,
    HelixError,
    ProgressHandlerError,
    RegistryCapacityError,
    SamsarixError,
    ToolDefinitionError,
    ToolNotFoundError,
)
from .mcp import MCPServer, serve_stdio
from .models import (
    RuntimeMetrics,
    TaskSupport,
    ToolCall,
    ToolCircuitBreaker,
    ToolCircuitState,
    ToolError,
    ToolLifecycleEvent,
    ToolLifecycleHandler,
    ToolLifecycleStatus,
    ToolPolicy,
    ToolPolicyContext,
    ToolPolicyDecision,
    ToolRateLimit,
    ToolResult,
    ToolSpec,
    ToolStatus,
)
from .progress import ProgressHandler, ToolProgress, report_progress
from .registry import ToolRegistry
from .runtime import ToolRuntime

__all__ = [
    "DuplicateToolError",
    "HelixError",
    "MCPServer",
    "ProgressHandler",
    "ProgressHandlerError",
    "RegistryCapacityError",
    "RuntimeMetrics",
    "SamsarixError",
    "TaskSupport",
    "ToolCall",
    "ToolCircuitBreaker",
    "ToolCircuitState",
    "ToolDefinitionError",
    "ToolError",
    "ToolLifecycleEvent",
    "ToolLifecycleHandler",
    "ToolLifecycleStatus",
    "ToolNotFoundError",
    "ToolPolicy",
    "ToolPolicyContext",
    "ToolPolicyDecision",
    "ToolProgress",
    "ToolRateLimit",
    "ToolRegistry",
    "ToolResult",
    "ToolRuntime",
    "ToolSpec",
    "ToolStatus",
    "__version__",
    "helix_tool",
    "report_progress",
    "samsarix_tool",
    "serve_stdio",
]
