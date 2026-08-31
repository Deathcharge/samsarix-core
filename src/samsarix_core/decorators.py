# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""The public decorator used to declare tool metadata."""

from __future__ import annotations

import inspect
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, overload

from ._timeouts import normalize_timeout
from .errors import ToolDefinitionError
from .models import TaskSupport
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
    title: str | None
    read_only: bool
    destructive: bool
    idempotent: bool
    open_world: bool
    task_support: TaskSupport


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
    title: str | None = None,
    read_only: bool = False,
    destructive: bool | None = None,
    idempotent: bool | None = None,
    open_world: bool = True,
    task_support: TaskSupport = "forbidden",
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
    title: str | None = None,
    read_only: bool = False,
    destructive: bool | None = None,
    idempotent: bool | None = None,
    open_world: bool = True,
    task_support: TaskSupport = "forbidden",
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
        normalized_timeout = normalize_timeout(timeout)
        if timeout is not None and normalized_timeout is None:
            raise ToolDefinitionError("Tool timeouts must be finite positive numbers")
        if not isinstance(version, str) or not version.strip():
            raise ToolDefinitionError("Tool versions must be non-empty strings")
        if any(not isinstance(tag, str) or not tag.strip() for tag in tags):
            raise ToolDefinitionError("Tool tags must be non-empty strings")
        if title is not None and (not isinstance(title, str) or not title.strip()):
            raise ToolDefinitionError("Tool titles must be non-empty strings")
        boolean_options = {
            "read_only": read_only,
            "open_world": open_world,
        }
        if destructive is not None:
            boolean_options["destructive"] = destructive
        if idempotent is not None:
            boolean_options["idempotent"] = idempotent
        invalid_option = next(
            (option for option, value in boolean_options.items() if not isinstance(value, bool)),
            None,
        )
        if invalid_option is not None:
            raise ToolDefinitionError(f"Tool option '{invalid_option}' must be a boolean")
        if task_support not in ("forbidden", "optional", "required"):
            raise ToolDefinitionError(
                "Tool task_support must be 'forbidden', 'optional', or 'required'"
            )

        destructive_hint = not read_only if destructive is None else destructive
        idempotent_hint = read_only if idempotent is None else idempotent
        if read_only and destructive_hint:
            raise ToolDefinitionError("Read-only tools cannot be marked destructive")

        compile_tool_contract(candidate)
        config = ToolConfig(
            name=tool_name,
            description=tool_description,
            timeout=normalized_timeout,
            version=version.strip(),
            tags=tuple(dict.fromkeys(tag.strip() for tag in tags)),
            title=title.strip() if title is not None else None,
            read_only=read_only,
            destructive=destructive_hint,
            idempotent=idempotent_hint,
            open_world=open_world,
            task_support=task_support,
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
