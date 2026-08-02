# Copyright 2026 Samsarix LLC
# SPDX-License-Identifier: MPL-2.0

"""Public exceptions raised at Samsarix Core's host-facing boundaries."""

from __future__ import annotations

from dataclasses import dataclass


class SamsarixError(Exception):
    """Base class for Samsarix Core exceptions."""


# Compatibility name retained for the pre-Samsarix public API.
HelixError = SamsarixError


class ToolDefinitionError(SamsarixError, ValueError):
    """Raised when a callable cannot form a valid tool contract."""


class DuplicateToolError(SamsarixError, ValueError):
    """Raised when a registry already contains a tool name."""


class RegistryCapacityError(SamsarixError, ValueError):
    """Raised when a registry has reached its configured tool limit."""


class ToolNotFoundError(SamsarixError, KeyError):
    """Raised by direct registry lookups for an unknown tool."""


class ProgressHandlerError(SamsarixError, RuntimeError):
    """Raised when an invocation's host-owned progress callback fails."""


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One safe, structured argument-validation problem."""

    path: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return a JSON-compatible representation."""

        return {"path": self.path, "code": self.code, "message": self.message}


class ToolArgumentError(SamsarixError, ValueError):
    """Raised internally when invocation arguments violate a tool contract."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


class ToolOutputError(SamsarixError, TypeError):
    """Raised internally when a tool returns a non-JSON-compatible value."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "invalid_output",
        public_message: str = "Tool returned a value that is not JSON-compatible",
    ) -> None:
        self.code = code
        self.public_message = public_message
        super().__init__(message)
