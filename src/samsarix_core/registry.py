# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Thread-safe registration and inspection of local tool callables."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from threading import RLock
from typing import Any

from .decorators import get_tool_config
from .errors import DuplicateToolError, RegistryCapacityError, ToolNotFoundError
from .models import JSONValue, ToolSpec
from .schema import compile_tool_contract


@dataclass(frozen=True, slots=True)
class RegisteredTool:
    """Internal callable plus its compiled contract."""

    function: Callable[..., Any]
    signature: inspect.Signature
    hints: dict[str, Any]
    spec: ToolSpec


class ToolRegistry:
    """A small explicit registry with deterministic schema export."""

    def __init__(self, *, max_tools: int = 256) -> None:
        if isinstance(max_tools, bool) or not isinstance(max_tools, int):
            raise TypeError("max_tools must be an integer")
        if max_tools <= 0:
            raise ValueError("max_tools must be positive")
        self.max_tools = max_tools
        self._tools: dict[str, RegisteredTool] = {}
        self._lock = RLock()

    def register(self, function: Callable[..., Any], *, replace: bool = False) -> ToolSpec:
        """Register a decorated callable and return its compiled contract."""

        config = get_tool_config(function)
        with self._lock:
            if config.name in self._tools and not replace:
                raise DuplicateToolError(f"Tool '{config.name}' is already registered")
            if config.name not in self._tools and len(self._tools) >= self.max_tools:
                raise RegistryCapacityError(
                    f"Registry capacity of {self.max_tools} tools has been reached"
                )

        signature, hints, input_schema, output_schema = compile_tool_contract(function)
        spec = ToolSpec(
            name=config.name,
            description=config.description,
            input_schema=input_schema,
            output_schema=output_schema,
            timeout=config.timeout,
            version=config.version,
            tags=config.tags,
            is_async=inspect.iscoroutinefunction(function),
            title=config.title,
            read_only=config.read_only,
            destructive=config.destructive,
            idempotent=config.idempotent,
            open_world=config.open_world,
        )
        registered = RegisteredTool(function=function, signature=signature, hints=hints, spec=spec)
        with self._lock:
            # Recheck after compilation in case another thread filled the registry.
            if config.name in self._tools and not replace:
                raise DuplicateToolError(f"Tool '{config.name}' is already registered")
            if config.name not in self._tools and len(self._tools) >= self.max_tools:
                raise RegistryCapacityError(
                    f"Registry capacity of {self.max_tools} tools has been reached"
                )
            self._tools[config.name] = registered
        return deepcopy(spec)

    def unregister(self, name: str) -> ToolSpec:
        """Remove a tool and return its former contract."""

        with self._lock:
            try:
                return deepcopy(self._tools.pop(name).spec)
            except KeyError as exc:
                raise ToolNotFoundError(name) from exc

    def get(self, name: str) -> ToolSpec:
        """Return a tool contract or raise :class:`ToolNotFoundError`."""

        return deepcopy(self._resolve(name).spec)

    def _resolve(self, name: str) -> RegisteredTool:
        """Return the internal immutable registration for runtime use."""

        with self._lock:
            try:
                return self._tools[name]
            except KeyError as exc:
                raise ToolNotFoundError(name) from exc

    def list(self) -> tuple[ToolSpec, ...]:
        """Return contracts sorted by tool name."""

        with self._lock:
            return tuple(deepcopy(self._tools[name].spec) for name in sorted(self._tools))

    def schema_catalog(self) -> dict[str, JSONValue]:
        """Export all contracts as deterministic JSON-compatible data."""

        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "tools": [deepcopy(spec.to_dict()) for spec in self.list()],
        }

    def __contains__(self, name: object) -> bool:
        with self._lock:
            return name in self._tools

    def __len__(self) -> int:
        with self._lock:
            return len(self._tools)
