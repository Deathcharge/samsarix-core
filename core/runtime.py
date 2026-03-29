"""
Helix Core - Agent Runtime

Manages the runtime state and lifecycle of agents.
"""

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    Manages agent runtime state and lifecycle.
    """

    def __init__(self):
        self._agents: dict[str, dict[str, Any]] = {}
        self._started_at = datetime.now(UTC)
        self._is_running = False

    async def start(self):
        """Start the agent runtime."""
        if self._is_running:
            logger.warning("AgentRuntime already started")
            return

        self._is_running = True
        logger.info("AgentRuntime started")

    async def stop(self):
        """Stop the agent runtime."""
        if not self._is_running:
            logger.warning("AgentRuntime not running")
            return

        self._is_running = False
        logger.info("AgentRuntime stopped")

    def is_running(self) -> bool:
        """Check if runtime is running."""
        return self._is_running

    def get_agent_count(self) -> int:
        """Get the number of registered agents."""
        return len(self._agents)

    def get_uptime_seconds(self) -> float:
        """Get runtime uptime in seconds."""
        return (datetime.now(UTC) - self._started_at).total_seconds()

    async def health_check(self) -> dict[str, Any]:
        """Perform a health check."""
        return {
            "status": "healthy" if self._is_running else "stopped",
            "agent_count": self.get_agent_count(),
            "uptime_seconds": self.get_uptime_seconds(),
            "timestamp": datetime.now(UTC).isoformat(),
        }
