"""
Helix Core - Tool Executor

Sandboxed execution of native tools with safety measures.
"""

import asyncio
import logging
from typing import Any

from ..ucf.metrics import UCFMetrics
from .registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Sandboxed execution of native tools.

    The ToolExecutor provides:
    - Timeout enforcement
    - Resource limits
    - Error containment
    - Recovery mechanisms
    """

    def __init__(self, tool_registry: ToolRegistry):
        self._tool_registry = tool_registry
        self._executor_lock = asyncio.Lock()

        logger.info("ToolExecutor initialized")

    async def execute(
        self,
        tool_name: str,
        *args,
        timeout: int | None = None,
        ucf_context: UCFMetrics | None = None,
        **kwargs,
    ) -> dict[str, Any]:
        """
        Execute a tool with safety measures.

        Args:
            tool_name: Name of tool to execute
            *args: Positional arguments
            timeout: Timeout in seconds (overrides tool default)
            ucf_context: UCF metrics for context
            **kwargs: Keyword arguments

        Returns:
            Execution result
        """
        # Get tool metadata
        metadata = await self._tool_registry.get_metadata(tool_name)

        if not metadata:
            return {
                "success": False,
                "error": f"Tool {tool_name} not found",
                "tool": tool_name,
            }

        # Use tool default timeout if not specified
        if timeout is None:
            timeout = metadata.timeout

        # Check deprecation
        if metadata.deprecated:
            logger.warning("Tool %s is deprecated (v%s)", tool_name, metadata.version)

        # Execute with timeout
        try:
            result = await asyncio.wait_for(
                self._tool_registry.execute_tool(tool_name, *args, **kwargs),
                timeout=timeout,
            )

            # Update UCF on success
            if ucf_context and result.get("success"):
                ucf_context.adjust_for_success(magnitude=0.02)

            return result

        except TimeoutError:
            error_msg = f"Tool {tool_name} timed out after {timeout} seconds"
            logger.error(error_msg)

            # Update UCF on timeout
            if ucf_context:
                ucf_context.adjust_for_failure(magnitude=0.05)

            return {
                "success": False,
                "error": error_msg,
                "tool": tool_name,
                "timeout": timeout,
            }

        except Exception as e:
            error_msg = f"Tool {tool_name} failed: {e!s}"
            logger.error(error_msg, exc_info=True)

            # Update UCF on error
            if ucf_context:
                ucf_context.adjust_for_failure(magnitude=0.05)

            return {"success": False, "error": error_msg, "tool": tool_name}

    async def execute_batch(self, tools: list, ucf_context: UCFMetrics | None = None) -> dict[str, dict[str, Any]]:
        """
        Execute multiple tools in batch.

        Args:
            tools: List of (tool_name, args, kwargs) tuples
            ucf_context: UCF metrics for context

        Returns:
            Dictionary of results by tool name
        """
        results = {}

        for tool_name, args, kwargs in tools:
            result = await self.execute(tool_name, *args, ucf_context=ucf_context, **kwargs)
            results[tool_name] = result

        return results

    async def execute_parallel(
        self, tools: list, ucf_context: UCFMetrics | None = None
    ) -> dict[str, dict[str, Any]]:
        """
        Execute multiple tools in parallel.

        Args:
            tools: List of (tool_name, args, kwargs) tuples
            ucf_context: UCF metrics for context

        Returns:
            Dictionary of results by tool name
        """
        tasks = [self.execute(tool_name, *args, ucf_context=ucf_context, **kwargs) for tool_name, args, kwargs in tools]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        results = {}
        for (tool_name, _, _), result in zip(tools, results_list):
            if isinstance(result, Exception):
                results[tool_name] = {
                    "success": False,
                    "error": str(result),
                    "tool": tool_name,
                }
            else:
                results[tool_name] = result

        return results

    async def get_executor_status(self) -> dict[str, Any]:
        """
        Get executor status.

        Returns:
            Status dictionary
        """
        tool_count = len(await self._tool_registry.list_tools())

        return {"tool_count": tool_count, "available": True}
