"""
Helix Core - UCF Adapter

Adapter for integrating UCF with external systems and legacy code.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from .metrics import UCFMetrics
from .store import UCFStore

logger = logging.getLogger(__name__)


class UCFAdapter:
    """
    Adapter for integrating UCF with external systems.

    The UCFAdapter provides:
    - Legacy system integration
    - External API bridging
    - Data transformation
    - Event synchronization
    """

    def __init__(self, ucf_store: UCFStore):
        self._ucf_store = ucf_store
        self._event_handlers: dict[str, list[callable]] = {}
        self._adapter_lock = asyncio.Lock()

        logger.info("UCFAdapter initialized")

    async def sync_from_legacy(self, agent_id: str, legacy_data: dict[str, Any]) -> UCFMetrics:
        """
        Sync UCF metrics from legacy system data.

        Args:
            agent_id: Agent ID
            legacy_data: Legacy system data

        Returns:
            UCF metrics
        """
        # Map legacy data to UCF metrics
        metrics = UCFMetrics()

        if "velocity" in legacy_data:
            metrics.velocity = float(legacy_data["velocity"])

        if "harmony" in legacy_data:
            metrics.harmony = float(legacy_data["harmony"])

        if "resilience" in legacy_data:
            metrics.resilience = float(legacy_data["resilience"])

        if "throughput" in legacy_data:
            metrics.throughput = float(legacy_data["throughput"])

        if "focus" in legacy_data:
            metrics.focus = float(legacy_data["focus"])

        if "friction" in legacy_data:
            metrics.friction = float(legacy_data["friction"])

        # Store in UCF store
        await self._ucf_store.set_metrics(agent_id, metrics)

        # Emit event
        await self._emit_event("sync_from_legacy", agent_id, metrics)

        logger.info("Synced UCF metrics from legacy for agent %s", agent_id)
        return metrics

    async def sync_to_legacy(self, agent_id: str) -> dict[str, Any] | None:
        """
        Sync UCF metrics to legacy system format.

        Args:
            agent_id: Agent ID

        Returns:
            Legacy format data
        """
        metrics = await self._ucf_store.get_metrics(agent_id)

        if not metrics:
            logger.warning("No metrics found for agent %s", agent_id)
            return None

        # Convert to legacy format
        legacy_data = {
            "velocity": metrics.velocity,
            "harmony": metrics.harmony,
            "resilience": metrics.resilience,
            "throughput": metrics.throughput,
            "focus": metrics.focus,
            "friction": metrics.friction,
            "timestamp": metrics.timestamp.isoformat(),
            "score": metrics.calculate_score(),
        }

        # Emit event
        await self._emit_event("sync_to_legacy", agent_id, metrics)

        logger.info("Synced UCF metrics to legacy for agent %s", agent_id)
        return legacy_data

    async def transform_from_langchain_memory(
        self, agent_id: str, langchain_memory: list[dict]
    ) -> list[dict[str, Any]]:
        """
        Transform LangChain memory to UCF-compatible format.

        Args:
            agent_id: Agent ID
            langchain_memory: LangChain memory data

        Returns:
            Transformed memory entries
        """
        transformed = []

        for entry in langchain_memory:
            transformed_entry = {
                "content": entry.get("content", ""),
                "timestamp": entry.get("timestamp", datetime.now(UTC).isoformat()),
                "metadata": {
                    "ucf_score": 0.85,  # Default score
                    "original_format": "langchain",
                },
            }

            if "metadata" in entry:
                transformed_entry["metadata"].update(entry["metadata"])

            transformed.append(transformed_entry)

        logger.info("Transformed %s LangChain memory entries for agent %s", len(transformed), agent_id)
        return transformed

    async def create_snapshot(self, agent_id: str) -> dict[str, Any]:
        """
        Create a snapshot of current UCF state.

        Args:
            agent_id: Agent ID

        Returns:
            Snapshot data
        """
        metrics = await self._ucf_store.get_metrics(agent_id)
        history = await self._ucf_store.get_history(agent_id, limit=50)

        snapshot = {
            "agent_id": agent_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "current_metrics": metrics.to_dict() if metrics else None,
            "history_length": len(history),
            "history": [m.to_dict() for m in history[-10:]],  # Last 10 entries
            "score": metrics.calculate_score() if metrics else 0.0,
            "healthy": metrics.is_healthy() if metrics else False,
        }

        logger.info("Created snapshot for agent %s", agent_id)
        return snapshot

    async def restore_from_snapshot(self, snapshot: dict[str, Any]) -> bool:
        """
        Restore UCF state from snapshot.

        Args:
            snapshot: Snapshot data

        Returns:
            True if successful
        """
        try:
            agent_id = snapshot["agent_id"]

            if "current_metrics" in snapshot:
                metrics = UCFMetrics.from_dict(snapshot["current_metrics"])
                await self._ucf_store.set_metrics(agent_id, metrics)

            logger.info("Restored UCF state from snapshot for agent %s", agent_id)
            return True

        except Exception as e:
            logger.error("Failed to restore from snapshot: %s", e, exc_info=True)
            return False

    async def subscribe_to_events(self, event_type: str, handler: callable):
        """
        Subscribe to UCF events.

        Args:
            event_type: Type of event
            handler: Event handler function
        """
        async with self._adapter_lock:
            if event_type not in self._event_handlers:
                self._event_handlers[event_type] = []

            self._event_handlers[event_type].append(handler)

        logger.info("Subscribed to event type: %s", event_type)

    async def _emit_event(self, event_type: str, agent_id: str, metrics: UCFMetrics):
        """Emit an event to subscribers."""
        async with self._adapter_lock:
            handlers = self._event_handlers.get(event_type, [])

        for handler in handlers:
            try:
                await handler(event_type, agent_id, metrics)
            except Exception as e:
                logger.error("Error in event handler: %s", e, exc_info=True)

    async def get_adapter_status(self) -> dict[str, Any]:
        """
        Get adapter status.

        Returns:
            Status dictionary
        """
        async with self._adapter_lock:
            return {
                "event_types": list(self._event_handlers.keys()),
                "handler_count": sum(len(h) for h in self._event_handlers.values()),
                "agents_count": len(await self._ucf_store.get_all_agents()),
            }
