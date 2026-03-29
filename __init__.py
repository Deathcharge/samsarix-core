"""
Helix Core - Unified Agent Runtime and Orchestration Framework
=============================================================

This module provides a unified entry point for Helix Flow and Helix Circle,
integrating with the Universal Coordination Framework (UCF).

Features:
- Unified agent runtime
- Flow and Circle orchestration
- UCF coordination integration
- Multi-agent coordination

Usage:
    from helix_core import HelixRuntime, create_flow_runtime, create_circle_runtime

    # Create a runtime
    runtime = HelixRuntime()

    # Run a flow
    result = await runtime.execute_flow(flow_definition, inputs)

    # Run a crew
    result = await runtime.execute_crew(crew_definition, task)

Copyright (c) 2025-2026 Helix Collective. All Rights Reserved.
"""

import logging
from typing import Any, Dict, List

from .adapter import HelixCoreAdapter
from .llm_bridge import HelixCoreLLMBridge

logger = logging.getLogger(__name__)

# =============================================================================
# VERSION
# =============================================================================

__version__ = "1.0.0"
__author__ = "Helix Collective"


# =============================================================================
# CORE COMPONENTS
# =============================================================================


class HelixRuntime:
    """
    Unified Helix Runtime for executing flows and crews.

    This is the main entry point for Helix Flow and Helix Circle,
    providing a consistent API for both while integrating with UCF.

    Example:
        runtime = HelixRuntime()

        # Execute a flow
        flow_result = await runtime.execute_flow(
            flow_id="my-flow",
            inputs={"query": "Analyze this code"}
        )

        # Execute a crew
        crew_result = await runtime.execute_crew(
            crew_id="my-crew",
            task="Build a REST API"
        )
    """

    def __init__(
        self,
        ucf_enabled: bool = True,
        memory_backend: str = "memory",
        llm_provider: str = "auto",
    ):
        self.ucf_enabled = ucf_enabled
        self.memory_backend = memory_backend
        self.llm_provider = llm_provider

        # Initialize components
        self._adapter = HelixCoreAdapter()
        self._llm_bridge = HelixCoreLLMBridge(provider=llm_provider)

        # Runtime state
        self._active_flows: dict[str, Any] = {}
        self._active_crews: dict[str, Any] = {}

        logger.info("HelixRuntime initialized (UCF: %s, LLM: %s)", ucf_enabled, llm_provider)

    async def execute_flow(
        self,
        flow_id: str,
        inputs: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a Helix Flow.

        Args:
            flow_id: ID of the flow to execute
            inputs: Input variables for the flow
            context: Optional execution context

        Returns:
            Execution result with output and metadata
        """
        # Check UCF state before execution
        ucf_state = {}
        if self.ucf_enabled:
            ucf_state = await self._get_ucf_state()
            logger.info("UCF state before flow: harmony=%.2f", ucf_state.get("harmony", 0))

        # Import and execute flow
        try:
            try:
                from apps.backend.helix_flow import PromptTemplate, SequentialChain
            except ImportError:
                from helix_flow import PromptTemplate, SequentialChain

            # Create flow chain
            chain = SequentialChain(
                name=flow_id,
                steps=[
                    PromptTemplate(template="Process: {input}"),
                ],
            )

            # Execute
            result = await chain.run(input_data=inputs)

            # Log UCF state after execution
            if self.ucf_enabled:
                await self._update_ucf_state("flow_execution", result.success)

            return {
                "success": result.success,
                "output": result.output,
                "flow_id": flow_id,
                "steps_executed": result.steps_executed,
                "execution_time_ms": result.execution_time_ms,
                "ucf_state": ucf_state,
            }

        except ImportError as e:
            logger.error("Helix Flow not available: %s", e)
            return {"success": False, "error": str(e)}

    async def execute_crew(
        self,
        crew_id: str,
        task: str,
        agents: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Execute a Helix Circle crew.

        Args:
            crew_id: ID of the crew to execute
            task: Task description
            agents: Optional list of agent IDs to use
            context: Optional execution context

        Returns:
            Execution result with output and metadata
        """
        # Check UCF state before execution
        ucf_state = {}
        if self.ucf_enabled:
            ucf_state = await self._get_ucf_state()
            logger.info("UCF state before crew: harmony=%.2f", ucf_state.get("harmony", 0))

        # Import and execute crew
        try:
            try:
                from apps.backend.helix_circle import Crew
            except ImportError:
                from helix_circle import Crew

            # Create crew
            crew = Crew(
                name=crew_id,
                agents=agents or [],
                task=task,
            )

            # Execute
            result = await crew.kickoff()

            # Log UCF state after execution
            if self.ucf_enabled:
                await self._update_ucf_state("crew_execution", result.get("success", False))

            return {
                "success": result.get("success", False),
                "output": result.get("output"),
                "crew_id": crew_id,
                "task": task,
                "agents_used": agents or [],
                "ucf_state": ucf_state,
            }

        except ImportError as e:
            logger.error("Helix Circle not available: %s", e)
            return {"success": False, "error": str(e)}

    async def _get_ucf_state(self) -> dict[str, Any]:
        """Get current UCF state for coordination-aware execution."""
        try:
            from apps.backend.global_state import get_current_ucf

            metrics = get_current_ucf()
            return {
                "harmony": metrics.get("harmony", 0.5),
                "resilience": metrics.get("resilience", 0.5),
                "throughput": metrics.get("throughput", 0.5),
            }
        except Exception as e:
            logger.warning("Could not get UCF state: %s", e)
            return {"harmony": 0.5, "resilience": 0.5, "throughput": 0.5}

    async def _update_ucf_state(self, action: str, success: bool) -> None:
        """Update UCF state after execution."""
        try:
            logger.info("UCF update: action=%s, success=%s", action, success)
        except Exception as e:
            logger.warning("Could not update UCF state: %s", e)

    def get_status(self) -> dict[str, Any]:
        """Get runtime status."""
        return {
            "version": __version__,
            "ucf_enabled": self.ucf_enabled,
            "llm_provider": self.llm_provider,
            "active_flows": len(self._active_flows),
            "active_crews": len(self._active_crews),
        }


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================


def create_flow_runtime(config: dict[str, Any] | None = None) -> HelixRuntime:
    """
    Create a HelixRuntime configured for Flow execution.

    Args:
        config: Optional configuration overrides

    Returns:
        Configured HelixRuntime instance
    """
    config = config or {}
    return HelixRuntime(
        ucf_enabled=config.get("ucf_enabled", True),
        memory_backend=config.get("memory_backend", "memory"),
        llm_provider=config.get("llm_provider", "auto"),
    )


def create_circle_runtime(config: dict[str, Any] | None = None) -> HelixRuntime:
    """
    Create a HelixRuntime configured for Circle execution.

    Args:
        config: Optional configuration overrides

    Returns:
        Configured HelixRuntime instance
    """
    config = config or {}
    return HelixRuntime(
        ucf_enabled=config.get("ucf_enabled", True),
        memory_backend=config.get("memory_backend", "vector"),
        llm_provider=config.get("llm_provider", "auto"),
    )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "HelixCoreAdapter",
    "HelixCoreLLMBridge",
    "HelixRuntime",
    "__version__",
    "create_circle_runtime",
    "create_flow_runtime",
]
