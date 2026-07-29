"""
Helix Core - UCF Store

Persistent storage for UCF metrics and history.
"""

import asyncio
import logging

from .metrics import UCFMetrics

logger = logging.getLogger(__name__)


class UCFStore:
    """
    Persistent storage for UCF metrics and history.

    The UCFStore provides:
    - Metric storage with history tracking
    - Query capabilities
    - Aggregation functions
    - Data persistence
    """

    def __init__(self, max_history: int = 1000):
        self._metrics: dict[str, UCFMetrics] = {}
        self._history: dict[str, list[UCFMetrics]] = {}
        self._max_history = max_history
        self._store_lock = asyncio.Lock()

        logger.info("UCFStore initialized")

    async def get_metrics(self, agent_id: str) -> UCFMetrics | None:
        """
        Get current metrics for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            UCF metrics or None
        """
        async with self._store_lock:
            return self._metrics.get(agent_id)

    async def set_metrics(self, agent_id: str, metrics: UCFMetrics):
        """
        Set metrics for an agent.

        Args:
            agent_id: Agent ID
            metrics: UCF metrics
        """
        async with self._store_lock:
            # Store old metrics in history
            if agent_id in self._metrics:
                if agent_id not in self._history:
                    self._history[agent_id] = []

                self._history[agent_id].append(self._metrics[agent_id])

                # Trim history
                if len(self._history[agent_id]) > self._max_history:
                    self._history[agent_id] = self._history[agent_id][-self._max_history :]

            # Set new metrics
            self._metrics[agent_id] = metrics.copy()

            logger.debug("Stored metrics for agent %s", agent_id)

    async def get_history(self, agent_id: str, limit: int = 100) -> list[UCFMetrics]:
        """
        Get metrics history for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of entries

        Returns:
            List of UCF metrics
        """
        async with self._store_lock:
            if agent_id not in self._history:
                return []

            return self._history[agent_id][-limit:]

    async def get_all_agents(self) -> list[str]:
        """
        Get all agent IDs with stored metrics.

        Returns:
            List of agent IDs
        """
        async with self._store_lock:
            return list(self._metrics.keys())

    async def delete_agent(self, agent_id: str):
        """
        Delete metrics for an agent.

        Args:
            agent_id: Agent ID
        """
        async with self._store_lock:
            self._metrics.pop(agent_id, None)
            self._history.pop(agent_id, None)

            logger.debug("Deleted metrics for agent %s", agent_id)

    async def get_aggregate_metrics(self) -> dict[str, float]:
        """
        Get aggregate metrics across all agents.

        Returns:
            Dictionary with aggregate metrics
        """
        async with self._store_lock:
            if not self._metrics:
                return {
                    "harmony": 0.0,
                    "resilience": 0.0,
                    "throughput": 0.0,
                    "focus": 0.0,
                    "friction": 0.0,
                    "count": 0,
                }

            metrics = list(self._metrics.values())

            return {
                "harmony": sum(m.harmony for m in metrics) / len(metrics),
                "resilience": sum(m.resilience for m in metrics) / len(metrics),
                "throughput": sum(m.throughput for m in metrics) / len(metrics),
                "focus": sum(m.focus for m in metrics) / len(metrics),
                "friction": sum(m.friction for m in metrics) / len(metrics),
                "count": len(metrics),
            }

    async def export_to_dict(self) -> dict:
        """
        Export all stored data to dictionary.

        Returns:
            Dictionary with all metrics and history
        """
        async with self._store_lock:
            return {
                "metrics": {agent_id: metrics.to_dict() for agent_id, metrics in self._metrics.items()},
                "history": {agent_id: [m.to_dict() for m in history] for agent_id, history in self._history.items()},
            }

    async def import_from_dict(self, data: dict):
        """
        Import data from dictionary.

        Args:
            data: Dictionary with metrics and history
        """
        async with self._store_lock:
            if "metrics" in data:
                for agent_id, metrics_data in data["metrics"].items():
                    self._metrics[agent_id] = UCFMetrics.from_dict(metrics_data)

            if "history" in data:
                for agent_id, history_data in data["history"].items():
                    self._history[agent_id] = [UCFMetrics.from_dict(m) for m in history_data]

            logger.info("Imported data for %s agents", len(self._metrics))

    async def clear_all(self):
        """Clear all stored metrics and history."""
        async with self._store_lock:
            self._metrics.clear()
            self._history.clear()

        logger.info("Cleared all UCF store data")
