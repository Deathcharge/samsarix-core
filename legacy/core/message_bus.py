"""
Helix Core - Message Bus

Enables inter-agent communication via publish/subscribe and direct messaging.
"""

import asyncio
import logging
import time
import uuid
from collections.abc import Callable

from .base import Message, MessageType, UCFMetrics

logger = logging.getLogger(__name__)


class MessageBus:
    """
    Enables inter-agent communication through publish/subscribe and direct messaging.

    The MessageBus is responsible for:
    - Publish/subscribe messaging
    - Message routing
    - Synchronization between agents
    - Event broadcasting
    - Queue management
    """

    def __init__(self):
        self._subscribers: dict[str, set[Callable]] = {}
        self._message_queues: dict[str, list[Message]] = {}
        self._message_history: list[Message] = []
        self._max_history = 1000
        self._bus_lock = asyncio.Lock()
        self._bus_started = False

        logger.info("MessageBus initialized")

    async def start(self):
        """Start the message bus."""
        if self._bus_started:
            logger.warning("MessageBus already started")
            return

        self._bus_started = True
        logger.info("MessageBus started")

    async def stop(self):
        """Stop the message bus."""
        if not self._bus_started:
            logger.warning("MessageBus not started")
            return

        self._bus_started = False
        logger.info("MessageBus stopped")

    async def publish(self, topic: str, message: Message):
        """
        Publish a message to a topic.

        Args:
            topic: Topic to publish to
            message: Message to publish
        """
        async with self._bus_lock:
            if topic not in self._subscribers:
                logger.debug("No subscribers for topic: %s", topic)
                return

            # Add to history
            self._add_to_history(message)

            # Notify subscribers
            for handler in self._subscribers[topic]:
                try:
                    await handler(message)
                except Exception as e:
                    logger.error("Error in subscriber handler: %s", e, exc_info=True)

            logger.debug("Published message to topic: %s", topic)

    async def subscribe(self, topic: str, handler: Callable[[Message], None]):
        """
        Subscribe to a topic.

        Args:
            topic: Topic to subscribe to
            handler: Handler function for messages
        """
        async with self._bus_lock:
            if topic not in self._subscribers:
                self._subscribers[topic] = set()

            self._subscribers[topic].add(handler)
            logger.info("Subscribed to topic: %s", topic)

    async def unsubscribe(self, topic: str, handler: Callable[[Message], None]):
        """
        Unsubscribe from a topic.

        Args:
            topic: Topic to unsubscribe from
            handler: Handler function to remove
        """
        async with self._bus_lock:
            if topic in self._subscribers and handler in self._subscribers[topic]:
                self._subscribers[topic].remove(handler)

                if not self._subscribers[topic]:
                    del self._subscribers[topic]

                logger.info("Unsubscribed from topic: %s", topic)

    async def send_direct(
        self,
        sender: str,
        receiver: str,
        content: str,
        message_type: MessageType = MessageType.DIRECT,
        ucf_context: UCFMetrics | None = None,
        metadata: dict | None = None,
    ) -> Message:
        """
        Send a direct message to an agent.

        Args:
            sender: Sender agent ID
            receiver: Receiver agent ID
            content: Message content
            message_type: Type of message
            ucf_context: UCF metrics of sender
            metadata: Additional metadata

        Returns:
            Created message
        """
        message = Message(
            message_id=str(uuid.uuid4()),
            from_agent=sender,
            to_agent=receiver,
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )

        async with self._bus_lock:
            # Add to receiver's queue
            if receiver not in self._message_queues:
                self._message_queues[receiver] = []

            self._message_queues[receiver].append(message)
            self._add_to_history(message)

        logger.debug("Sent direct message from %s to %s", sender, receiver)
        return message

    async def broadcast(
        self,
        sender: str,
        content: str,
        message_type: MessageType = MessageType.BROADCAST,
        ucf_context: UCFMetrics | None = None,
        metadata: dict | None = None,
    ) -> Message:
        """
        Broadcast a message to all agents.

        Args:
            sender: Sender agent ID
            content: Message content
            message_type: Type of message
            ucf_context: UCF metrics of sender
            metadata: Additional metadata

        Returns:
            Created message
        """
        message = Message(
            message_id=str(uuid.uuid4()),
            from_agent=sender,
            to_agent="*",  # Broadcast target
            content=content,
            message_type=message_type,
            metadata=metadata or {},
        )

        # Publish to broadcast topic
        await self.publish("broadcast", message)

        logger.debug("Broadcasted message from %s", sender)
        return message

    async def receive(self, agent_id: str, timeout: float | None = None) -> Message | None:
        """
        Receive a message for an agent.

        Args:
            agent_id: Agent ID to receive messages for
            timeout: Timeout in seconds

        Returns:
            Message or None if timeout
        """
        start_time = time.monotonic()

        while True:
            async with self._bus_lock:
                if self._message_queues.get(agent_id):
                    return self._message_queues[agent_id].pop(0)

            # Check timeout
            if timeout:
                elapsed = time.monotonic() - start_time
                if elapsed >= timeout:
                    return None
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(0.1)

    async def receive_nowait(self, agent_id: str) -> Message | None:
        """
        Receive a message without waiting.

        Args:
            agent_id: Agent ID to receive messages for

        Returns:
            Message or None if no messages
        """
        async with self._bus_lock:
            if self._message_queues.get(agent_id):
                return self._message_queues[agent_id].pop(0)

        return None

    async def peek_messages(self, agent_id: str) -> list[Message]:
        """
        Peek at messages for an agent without removing them.

        Args:
            agent_id: Agent ID

        Returns:
            List of messages
        """
        async with self._bus_lock:
            if agent_id in self._message_queues:
                return self._message_queues[agent_id].copy()

        return []

    async def get_subscribers(self, topic: str) -> set[Callable]:
        """
        Get subscribers for a topic.

        Args:
            topic: Topic

        Returns:
            Set of subscriber handlers
        """
        async with self._bus_lock:
            return self._subscribers.get(topic, set()).copy()

    async def get_topics(self) -> list[str]:
        """
        Get all active topics.

        Returns:
            List of topic names
        """
        async with self._bus_lock:
            return list(self._subscribers.keys())

    async def get_history(
        self,
        limit: int = 100,
        sender: str | None = None,
        receiver: str | None = None,
    ) -> list[Message]:
        """
        Get message history.

        Args:
            limit: Maximum number of messages
            sender: Filter by sender
            receiver: Filter by receiver

        Returns:
            List of messages
        """
        async with self._bus_lock:
            messages = self._message_history

            if sender:
                messages = [m for m in messages if m.sender == sender]
            if receiver:
                messages = [m for m in messages if m.receiver == receiver]

            return messages[-limit:]

    async def clear_queue(self, agent_id: str):
        """
        Clear message queue for an agent.

        Args:
            agent_id: Agent ID
        """
        async with self._bus_lock:
            if agent_id in self._message_queues:
                self._message_queues[agent_id].clear()

        logger.debug("Cleared message queue for agent %s", agent_id)

    async def clear_history(self):
        """Clear message history."""
        async with self._bus_lock:
            self._message_history.clear()

        logger.info("Message history cleared")

    def _add_to_history(self, message: Message):
        """Add message to history."""
        self._message_history.append(message)

        # Trim history if needed
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history :]

    async def is_running(self) -> bool:
        """Check if message bus is running."""
        return self._bus_started
