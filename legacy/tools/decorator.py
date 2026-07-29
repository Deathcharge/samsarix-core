"""
Helix Core - Tool Decorator

@helix_tool decorator for defining native tools.
"""

import functools
import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ToolMetadata:
    """Metadata for a tool."""

    def __init__(
        self,
        name: str,
        description: str,
        version: str = "1.0.0",
        timeout: int = 30,
        ethics_check: bool = True,
        ucf_metrics: list[str] | None = None,
        tags: list[str] | None = None,
        author: str = "",
        deprecated: bool = False,
    ):
        self.name = name
        self.description = description
        self.version = version
        self.timeout = timeout
        self.ethics_check = ethics_check
        self.ucf_metrics = ucf_metrics or []
        self.tags = tags or []
        self.author = author
        self.deprecated = deprecated
        self.created_at = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "timeout": self.timeout,
            "ethics_check": self.ethics_check,
            "ucf_metrics": self.ucf_metrics,
            "tags": self.tags,
            "author": self.author,
            "deprecated": self.deprecated,
            "created_at": self.created_at.isoformat(),
        }


def helix_tool(
    name: str,
    description: str,
    version: str = "1.0.0",
    timeout: int = 30,
    ethics_check: bool = True,
    ucf_metrics: list[str] | None = None,
    tags: list[str] | None = None,
    author: str = "",
    deprecated: bool = False,
):
    """
    Decorator for defining native Helix tools.

    Args:
        name: Tool name
        description: Tool description
        version: Tool version
        timeout: Timeout in seconds
        ethics_check: Whether to perform ethics check
        ucf_metrics: UCF metrics to track
        tags: Tool tags
        author: Tool author
        deprecated: Whether tool is deprecated

    Example:
        @helix_tool(
            name="web_search",
            description="Search the web for information",
            timeout=30
        )
        async def web_search(query: str, num_results: int = 10) -> Dict:
            # Implementation
            pass
    """

    def decorator(func: Callable):
        # Create metadata
        metadata = ToolMetadata(
            name=name,
            description=description,
            version=version,
            timeout=timeout,
            ethics_check=ethics_check,
            ucf_metrics=ucf_metrics,
            tags=tags,
            author=author,
            deprecated=deprecated,
        )

        # Get function signature
        sig = inspect.signature(func)

        # Wrap function
        @functools.wraps(func)
        async def wrapped(*args, **kwargs):
            # Log tool execution
            logger.info("Executing tool: %s (v%s)", name, version)

            # Check if deprecated
            if deprecated:
                logger.warning("Tool %s is deprecated", name)

            # Execute function
            start_time = datetime.now(UTC)

            try:
                result = await func(*args, **kwargs)

                execution_time = (datetime.now(UTC) - start_time).total_seconds()

                logger.info("Tool %s completed in %.2fs", name, execution_time)

                return {
                    "success": True,
                    "result": result,
                    "execution_time": execution_time,
                    "tool": name,
                    "version": version,
                }

            except Exception as e:
                execution_time = (datetime.now(UTC) - start_time).total_seconds()

                logger.error(
                    f"Tool {name} failed after {execution_time:.2f}s: {e}",
                    exc_info=True,
                )

                return {
                    "success": False,
                    "error": str(e),
                    "execution_time": execution_time,
                    "tool": name,
                    "version": version,
                }

        # Add metadata to function
        wrapped._helix_tool_metadata = metadata
        wrapped._helix_tool_signature = sig

        return wrapped

    return decorator


def is_helix_tool(func: Callable) -> bool:
    """
    Check if a function is a Helix tool.

    Args:
        func: Function to check

    Returns:
        True if function is a Helix tool
    """
    return hasattr(func, "_helix_tool_metadata")


def get_tool_metadata(func: Callable) -> ToolMetadata | None:
    """
    Get metadata for a Helix tool.

    Args:
        func: Function to get metadata from

    Returns:
        ToolMetadata or None
    """
    if is_helix_tool(func):
        return func._helix_tool_metadata
    return None
