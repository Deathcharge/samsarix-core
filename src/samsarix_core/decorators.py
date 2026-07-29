# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""The public decorator used to declare tool metadata."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, overload

from .errors import ToolDefinitionError
from .schema import compile_tool_contract

F = TypeVar("F", bound=Callable[..., Any])
_TOOL_CONFIG_ATTRIBUTE = "__samsarix_tool_config__"
_TOOL_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{0,63}$")


@dataclass(frozen=True, slots=True)
class ToolConfig:
    """Metadata attached to a decorated callable."""

    name: str
    description: str
    timeout: float | None
    version: str
    tags: tuple[str, ...]


@overload
def samsarix_tool(function: F, /) -> F: ...


@overload
def samsarix_tool(
    function: None = None,
    /,
    *,
    name: str | None = None,
    description: str | None = None,
    timeout: float | None = None,
    version: str = "1",
    tags: tuple[str, ...] = (),
) -> Callable[[F], F]: ...


def samsarix_tool(
    function: F | None = None,
    /,
    *,
    name: str | None = None,
    description: str | None = None,
    timeout: float | None = None,
    version: str = "1",
    tags: tuple[str, ...] = (),
) -> F | Callable[[F], F]:
    """Declare a typed sync or async function as a Samsarix tool."""

    def decorate(candidate: F) -> F:
        tool_name = name or candidate.__name__
        if not _TOOL_NAME.fullmatch(tool_name):
            raise ToolDefinitionError(
                "Tool names must start with a letter, contain only letters, digits, '_' or '-', "
                "and be at most 64 characters"
            )

        doc = inspect.getdoc(candidate) or ""
        tool_description = (
            description or doc.splitlines()[0] if doc else description or ""
        ).strip()
        if not tool_description:
            raise ToolDefinitionError("Tools need a description or a non-empty docstring")
        if timeout is not None and (
            isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or timeout <= 0
        ):
            raise ToolDefinitionError("Tool timeouts must be positive numbers")
        if not isinstance(version, str) or not version.strip():
            raise ToolDefinitionError("Tool versions must be non-empty strings")
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ToolDefinitionError("Tool tags must be non-empty strings")

        compile_tool_contract(candidate)
        config = ToolConfig(
            name=tool_name,
            description=tool_description,
            timeout=float(timeout) if timeout is not None else None,
            version=version.strip(),
            tags=tuple(dict.fromkeys(tag.strip() for tag in tags)),
        )
        setattr(candidate, _TOOL_CONFIG_ATTRIBUTE, config)
        return candidate

    if function is not None:
        return decorate(function)
    return decorate


def get_tool_config(function: Callable[..., Any]) -> ToolConfig:
    """Read validated metadata from a decorated callable."""

    config = getattr(function, _TOOL_CONFIG_ATTRIBUTE, None)
    if not isinstance(config, ToolConfig):
        raise ToolDefinitionError("Register only callables decorated with @samsarix_tool")
    return config


# Compatibility name retained for the pre-Samsarix public API.
helix_tool = samsarix_tool
