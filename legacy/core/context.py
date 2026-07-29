"""
Helix Core - Context Manager

Centralized context and state management with UCF integration.
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .base import UCFMetrics

logger = logging.getLogger(__name__)


class ContextManager:
    """
    Centralized context and state management.

    The ContextManager is responsible for:
    - UCF metrics storage and tracking
    - Agent state persistence
    - Shared context management
    - Cross-agent awareness
    - Learning data storage
    """

    def __init__(self):
        # UCF storage
        self._ucf_metrics: dict[str, UCFMetrics] = {}
        self._ucf_history: dict[str, list[UCFMetrics]] = {}
        self._max_history_per_agent = 100

        # Agent state storage
        self._agent_states: dict[str, dict[str, Any]] = {}
        self._agent_memory: dict[str, list[dict[str, Any]]] = {}
        self._max_memory_per_agent = 500

        # Shared context
        self._shared_context: dict[str, Any] = {}
        self._context_timestamps: dict[str, datetime] = {}

        # Learning data
        self._learning_data: dict[str, list[dict[str, Any]]] = {}

        self._context_lock = asyncio.Lock()
        self._manager_started = False

        logger.info("ContextManager initialized")

    async def start(self):
        """Start the context manager."""
        if self._manager_started:
            logger.warning("ContextManager already started")
            return

        self._manager_started = True
        logger.info("ContextManager started")

    async def stop(self):
        """Stop the context manager."""
        if not self._manager_started:
            logger.warning("ContextManager not started")
            return

        self._manager_started = False
        logger.info("ContextManager stopped")

    # ==================== UCF Metrics ====================

    async def get_ucf_metrics(self, agent_id: str) -> UCFMetrics | None:
        """
        Get current UCF metrics for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            UCF metrics or None if not found
        """
        async with self._context_lock:
            return self._ucf_metrics.get(agent_id)

    async def update_ucf_metrics(self, agent_id: str, metrics: UCFMetrics):
        """
        Update UCF metrics for an agent.

        Args:
            agent_id: Agent ID
            metrics: New UCF metrics
        """
        async with self._context_lock:
            # Store old metrics in history
            if agent_id in self._ucf_metrics:
                if agent_id not in self._ucf_history:
                    self._ucf_history[agent_id] = []

                self._ucf_history[agent_id].append(self._ucf_metrics[agent_id])

                # Trim history
                if len(self._ucf_history[agent_id]) > self._max_history_per_agent:
                    self._ucf_history[agent_id] = self._ucf_history[agent_id][-self._max_history_per_agent :]

            # Update current metrics
            self._ucf_metrics[agent_id] = metrics

            logger.debug("Updated UCF metrics for agent %s", agent_id)

    async def get_ucf_history(self, agent_id: str, limit: int = 50) -> list[UCFMetrics]:
        """
        Get UCF metrics history for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of entries

        Returns:
            List of UCF metrics
        """
        async with self._context_lock:
            if agent_id not in self._ucf_history:
                return []

            return self._ucf_history[agent_id][-limit:]

    async def get_collective_ucf(self) -> dict[str, float]:
        """
        Get aggregate UCF metrics across all agents.

        Returns:
            Dictionary with aggregate metrics
        """
        async with self._context_lock:
            if not self._ucf_metrics:
                return {
                    "harmony": 0.0,
                    "resilience": 0.0,
                    "throughput": 0.0,
                    "focus": 0.0,
                    "friction": 0.0,
                    "count": 0,
                }

            metrics = list(self._ucf_metrics.values())

            return {
                "harmony": sum(m.harmony for m in metrics) / len(metrics),
                "resilience": sum(m.resilience for m in metrics) / len(metrics),
                "throughput": sum(m.throughput for m in metrics) / len(metrics),
                "focus": sum(m.focus for m in metrics) / len(metrics),
                "friction": sum(m.friction for m in metrics) / len(metrics),
                "count": len(metrics),
            }

    # ==================== Agent State ====================

    async def get_agent_state(self, agent_id: str) -> dict[str, Any] | None:
        """
        Get state for an agent.

        Args:
            agent_id: Agent ID

        Returns:
            Agent state or None if not found
        """
        async with self._context_lock:
            return self._agent_states.get(agent_id)

    async def set_agent_state(self, agent_id: str, state: dict[str, Any]):
        """
        Set state for an agent.

        Args:
            agent_id: Agent ID
            state: State dictionary
        """
        async with self._context_lock:
            self._agent_states[agent_id] = state.copy()
            state["updated_at"] = datetime.now(UTC).isoformat()

    async def update_agent_state(self, agent_id: str, updates: dict[str, Any]):
        """
        Update specific fields in agent state.

        Args:
            agent_id: Agent ID
            updates: Fields to update
        """
        async with self._context_lock:
            if agent_id not in self._agent_states:
                self._agent_states[agent_id] = {}

            self._agent_states[agent_id].update(updates)
            self._agent_states[agent_id]["updated_at"] = datetime.now(UTC).isoformat()

    async def delete_agent_state(self, agent_id: str):
        """
        Delete state for an agent.

        Args:
            agent_id: Agent ID
        """
        async with self._context_lock:
            self._agent_states.pop(agent_id, None)
            logger.debug("Deleted state for agent %s", agent_id)

    # ==================== Agent Memory ====================

    async def get_agent_memory(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """
        Get memory entries for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of entries

        Returns:
            List of memory entries
        """
        async with self._context_lock:
            if agent_id not in self._agent_memory:
                return []

            return self._agent_memory[agent_id][-limit:]

    async def add_memory(self, agent_id: str, memory: dict[str, Any]):
        """
        Add a memory entry for an agent.

        Args:
            agent_id: Agent ID
            memory: Memory entry
        """
        async with self._context_lock:
            if agent_id not in self._agent_memory:
                self._agent_memory[agent_id] = []

            memory["timestamp"] = datetime.now(UTC).isoformat()
            self._agent_memory[agent_id].append(memory)

            # Trim memory
            if len(self._agent_memory[agent_id]) > self._max_memory_per_agent:
                self._agent_memory[agent_id] = self._agent_memory[agent_id][-self._max_memory_per_agent :]

            logger.debug("Added memory for agent %s", agent_id)

    async def search_memory(self, agent_id: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
        """
        Search agent memory.

        Args:
            agent_id: Agent ID
            query: Search query
            limit: Maximum number of results

        Returns:
            List of matching memory entries
        """
        async with self._context_lock:
            if agent_id not in self._agent_memory:
                return []

            query_lower = query.lower()
            results = []

            for memory in self._agent_memory[agent_id]:
                # Simple text search
                content = str(memory.get("content", ""))
                if query_lower in content.lower():
                    results.append(memory)

                if len(results) >= limit:
                    break

            return results

    async def clear_memory(self, agent_id: str):
        """
        Clear memory for an agent.

        Args:
            agent_id: Agent ID
        """
        async with self._context_lock:
            self._agent_memory.pop(agent_id, None)
            logger.debug("Cleared memory for agent %s", agent_id)

    # ==================== Shared Context ====================

    async def get_shared_context(self, key: str) -> Any | None:
        """
        Get a value from shared context.

        Args:
            key: Context key

        Returns:
            Value or None if not found
        """
        async with self._context_lock:
            return self._shared_context.get(key)

    async def set_shared_context(self, key: str, value: Any, ttl: int | None = None):
        """
        Set a value in shared context.

        Args:
            key: Context key
            value: Value to store
            ttl: Time-to-live in seconds (None for no expiry)
        """
        async with self._context_lock:
            self._shared_context[key] = value
            self._context_timestamps[key] = datetime.now(UTC)

            if ttl:
                # Schedule deletion
                asyncio.create_task(self._expire_context(key, ttl))

    async def _expire_context(self, key: str, ttl: int):
        """Expire a context key after TTL."""
        await asyncio.sleep(ttl)
        async with self._context_lock:
            self._shared_context.pop(key, None)
            self._context_timestamps.pop(key, None)

    async def delete_shared_context(self, key: str):
        """
        Delete a value from shared context.

        Args:
            key: Context key
        """
        async with self._context_lock:
            self._shared_context.pop(key, None)
            self._context_timestamps.pop(key, None)

    async def get_all_shared_context(self) -> dict[str, Any]:
        """
        Get all shared context.

        Returns:
            Dictionary of all shared context
        """
        async with self._context_lock:
            return self._shared_context.copy()

    # ==================== Learning Data ====================

    async def add_learning_data(self, agent_id: str, experience: dict[str, Any]):
        """
        Add learning experience for an agent.

        Args:
            agent_id: Agent ID
            experience: Experience data
        """
        async with self._context_lock:
            if agent_id not in self._learning_data:
                self._learning_data[agent_id] = []

            experience["timestamp"] = datetime.now(UTC).isoformat()
            self._learning_data[agent_id].append(experience)

            logger.debug("Added learning data for agent %s", agent_id)

    async def get_learning_data(self, agent_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get learning data for an agent.

        Args:
            agent_id: Agent ID
            limit: Maximum number of entries

        Returns:
            List of learning experiences
        """
        async with self._context_lock:
            if agent_id not in self._learning_data:
                return []

            return self._learning_data[agent_id][-limit:]

    # ==================== Utility Methods ====================

    async def cleanup_old_data(self, older_than_days: int = 30):
        """
        Clean up old data.

        Args:
            older_than_days: Age in days
        """
        async with self._context_lock:
            cutoff = datetime.now(UTC) - timedelta(days=older_than_days)

            # Clean old memory entries
            for agent_id in self._agent_memory:
                self._agent_memory[agent_id] = [
                    m for m in self._agent_memory[agent_id] if datetime.fromisoformat(m["timestamp"]) > cutoff
                ]

            # Clean old learning data
            for agent_id in self._learning_data:
                self._learning_data[agent_id] = [
                    e for e in self._learning_data[agent_id] if datetime.fromisoformat(e["timestamp"]) > cutoff
                ]

            logger.info("Cleaned up data older than %s days", older_than_days)

    async def is_running(self) -> bool:
        """Check if context manager is running."""
        return self._manager_started
