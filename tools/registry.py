"""
Helix Core - Tool Registry

Automatic registration and management of native tools.
"""

import asyncio
import inspect
import logging
from collections.abc import Callable
from datetime import UTC, datetime

from .decorator import ToolMetadata, get_tool_metadata, is_helix_tool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    Registry for managing native Helix tools.

    The ToolRegistry provides:
    - Automatic tool discovery
    - Version management
    - Tool querying
    - Usage tracking
    """

    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._metadata: dict[str, ToolMetadata] = {}
        self._usage_stats: dict[str, dict[str, int]] = {}
        self._registry_lock = asyncio.Lock()

        logger.info("ToolRegistry initialized")

    async def register(self, func: Callable) -> bool:
        """
        Register a tool function.

        Args:
            func: Tool function

        Returns:
            True if registered successfully
        """
        if not is_helix_tool(func):
            logger.warning("Function %s is not a Helix tool", func.__name__)
            return False

        metadata = get_tool_metadata(func)

        if not metadata:
            logger.error("Could not get metadata for function %s", func.__name__)
            return False

        async with self._registry_lock:
            # Check for existing tool with same name
            if metadata.name in self._tools:
                existing_metadata = self._metadata[metadata.name]

                # Check version
                if metadata.version == existing_metadata.version:
                    logger.warning("Tool %s v%s already registered", metadata.name, metadata.version)
                    return False
                else:
                    logger.info(
                        f"Updating tool {metadata.name} from v{existing_metadata.version} to v{metadata.version}"
                    )

            # Register tool
            self._tools[metadata.name] = func
            self._metadata[metadata.name] = metadata
            self._usage_stats[metadata.name] = {
                "total_calls": 0,
                "successful_calls": 0,
                "failed_calls": 0,
                "last_used": None,
            }

            logger.info("Registered tool: %s v%s", metadata.name, metadata.version)
            return True

    async def unregister(self, name: str) -> bool:
        """
        Unregister a tool.

        Args:
            name: Tool name

        Returns:
            True if unregistered successfully
        """
        async with self._registry_lock:
            if name not in self._tools:
                logger.warning("Tool %s not found", name)
                return False

            del self._tools[name]
            del self._metadata[name]
            del self._usage_stats[name]

            logger.info("Unregistered tool: %s", name)
            return True

    async def get_tool(self, name: str) -> Callable | None:
        """
        Get a tool function by name.

        Args:
            name: Tool name

        Returns:
            Tool function or None
        """
        return self._tools.get(name)

    async def get_metadata(self, name: str) -> ToolMetadata | None:
        """
        Get metadata for a tool.

        Args:
            name: Tool name

        Returns:
            ToolMetadata or None
        """
        return self._metadata.get(name)

    async def list_tools(
        self,
        tags: list[str] | None = None,
        author: str | None = None,
        include_deprecated: bool = False,
    ) -> list[ToolMetadata]:
        """
        List all registered tools.

        Args:
            tags: Filter by tags
            author: Filter by author
            include_deprecated: Include deprecated tools

        Returns:
            List of tool metadata
        """
        async with self._registry_lock:
            tools = []

            for metadata in self._metadata.values():
                # Filter deprecated
                if not include_deprecated and metadata.deprecated:
                    continue

                # Filter by tags
                if tags and not any(tag in metadata.tags for tag in tags):
                    continue

                # Filter by author
                if author and metadata.author != author:
                    continue

                tools.append(metadata)

            return tools

    async def execute_tool(self, name: str, *args, **kwargs) -> dict:
        """
        Execute a tool.

        Args:
            name: Tool name
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Execution result
        """
        func = await self.get_tool(name)

        if not func:
            return {"success": False, "error": f"Tool {name} not found"}

        # Track usage
        async with self._registry_lock:
            self._usage_stats[name]["total_calls"] += 1
            self._usage_stats[name]["last_used"] = datetime.now(UTC).isoformat()

        # Execute
        try:
            result = await func(*args, **kwargs)

            # Track success
            async with self._registry_lock:
                self._usage_stats[name]["successful_calls"] += 1

            return result

        except Exception as e:
            logger.error("Error executing tool %s: %s", name, e, exc_info=True)

            # Track failure
            async with self._registry_lock:
                self._usage_stats[name]["failed_calls"] += 1

            return {"success": False, "error": str(e), "tool": name}

    async def get_usage_stats(self, name: str) -> dict[str, int] | None:
        """
        Get usage statistics for a tool.

        Args:
            name: Tool name

        Returns:
            Usage statistics or None
        """
        return self._usage_stats.get(name)

    async def get_all_usage_stats(self) -> dict[str, dict[str, int]]:
        """
        Get usage statistics for all tools.

        Returns:
            Dictionary of usage statistics
        """
        return self._usage_stats.copy()

    async def auto_discover(self, module: any) -> int:
        """
        Auto-discover tools in a module.

        Args:
            module: Module to search

        Returns:
            Number of tools discovered
        """
        count = 0

        for name, obj in inspect.getmembers(module):
            if inspect.isfunction(obj) and is_helix_tool(obj):
                await self.register(obj)
                count += 1

        logger.info("Auto-discovered %s tools in module %s", count, module.__name__)
        return count

    async def export_registry(self) -> dict:
        """
        Export registry to dictionary.

        Returns:
            Dictionary with registry data
        """
        async with self._registry_lock:
            return {
                "tools": {name: metadata.to_dict() for name, metadata in self._metadata.items()},
                "usage_stats": self._usage_stats.copy(),
                "count": len(self._tools),
            }

    async def clear_registry(self):
        """Clear all registered tools."""
        async with self._registry_lock:
            self._tools.clear()
            self._metadata.clear()
            self._usage_stats.clear()

        logger.info("Cleared tool registry")
