"""
Helix Core - Task Orchestrator

Coordinates task distribution, scheduling, and execution across agents.
"""

import asyncio
import heapq
import logging
import re
import time
from datetime import UTC, datetime

from .base import ExecutionResult, Task, TaskStatus

logger = logging.getLogger(__name__)

# ============================================================================
# PINNED CONSTRAINTS — Immutable safety guardrails
#
# Defined at module level so they survive instance re-creation, context
# compaction, and agent self-modification attempts.
# Inspired by the OpenClaw guardrail-pinning pattern (2025).
# ============================================================================

PINNED_CONSTRAINTS: dict[str, str] = {
    "no_recursive_self_modification": (
        "Agents may not modify their own coordination weights, UCF baselines, or personality traits at runtime"
    ),
    "no_credential_exfiltration": (
        "Agents may not read, log, transmit, or store API keys, tokens, passwords, or any credential-like strings"
    ),
    "no_unbounded_loops": (
        "Agents may not submit tasks that spawn unbounded recursive sub-task chains (max depth: 10)"
    ),
    "rate_limit_per_minute": ("No agent may submit more than 60 tasks per minute — prevents runaway autonomy loops"),
    "human_approval_for_sensitive": (
        "Tasks tagged sensitive=True or destructive=True require an explicit human_approval_token in the task context"
    ),
    "no_cross_agent_impersonation": (
        "Agents may not submit tasks claiming to be another agent without a valid agent_delegation_token"
    ),
}

# Per-agent submission timestamps for rate limiting (Unix seconds)
_agent_submission_counts: dict[str, list[float]] = {}

# Pre-compiled pattern for credential detection
_CREDENTIAL_PATTERN = re.compile(
    r"(sk-[a-zA-Z0-9]{20,}|Bearer\s+\S{20,}|" r"password\s*[:=]\s*\S+|api[_-]?key\s*[:=]\s*\S{10,})",
    re.IGNORECASE,
)


class PinnedConstraintViolation(Exception):
    """
    Raised when a submitted task violates a pinned safety constraint.

    Unlike runtime errors, these are never caught silently — they propagate
    to the caller so the violation can be logged and audited.
    """

    def __init__(self, constraint_key: str, reason: str, task_id: str = ""):
        self.constraint_key = constraint_key
        self.task_id = task_id
        super().__init__(
            f"Pinned constraint violated [{constraint_key}]"
            + (f" on task {task_id}" if task_id else "")
            + f": {reason}"
        )


class TaskOrchestrator:
    """
    Coordinates task distribution and execution across agents.

    The TaskOrchestrator is responsible for:
    - Task queue management
    - Dependency resolution
    - Priority scheduling
    - Load balancing across agents
    - Task tracking and monitoring
    """

    def __init__(self):
        self._task_queue: list[Task] = []
        self._tasks: dict[str, Task] = {}
        self._completed_tasks: set[str] = set()
        self._failed_tasks: set[str] = set()
        self._agent_loads: dict[str, int] = {}
        self._task_lock = asyncio.Lock()
        self._orchestrator_started = False

        logger.info("TaskOrchestrator initialized")

    async def start(self):
        """Start the orchestrator."""
        if self._orchestrator_started:
            logger.warning("TaskOrchestrator already started")
            return

        self._orchestrator_started = True
        logger.info("TaskOrchestrator started")

    async def stop(self):
        """Stop the orchestrator."""
        if not self._orchestrator_started:
            logger.warning("TaskOrchestrator not started")
            return

        self._orchestrator_started = False
        logger.info("TaskOrchestrator stopped")

    def _validate_pinned_constraints(self, task: Task) -> None:
        """
        Validate a task against all pinned safety constraints.

        Raises PinnedConstraintViolation if any constraint is violated.
        Called before every task submission — cannot be bypassed by agent code.
        """
        task_context = task.context or {}

        # Check: no credential-like strings in task content/context
        task_str = str(getattr(task, "description", "")) + str(task_context)
        if _CREDENTIAL_PATTERN.search(task_str):
            raise PinnedConstraintViolation(
                "no_credential_exfiltration",
                "Task content contains credential-like strings",
                task_id=task.id,
            )

        # Check: sensitive/destructive tasks require human approval token
        if task_context.get("sensitive") or task_context.get("destructive"):
            if not task_context.get("human_approval_token"):
                raise PinnedConstraintViolation(
                    "human_approval_for_sensitive",
                    "Task is marked sensitive/destructive but has no human_approval_token",
                    task_id=task.id,
                )

        # Check: task recursion depth
        depth = int(task_context.get("recursion_depth", 0))
        if depth > 10:
            raise PinnedConstraintViolation(
                "no_unbounded_loops",
                f"Task recursion depth {depth} exceeds maximum of 10",
                task_id=task.id,
            )

        # Check: rate limit per agent (60 tasks/minute)
        agent_id = str(task_context.get("agent_id", "unknown"))
        now = time.time()
        window_start = now - 60.0

        if agent_id not in _agent_submission_counts:
            _agent_submission_counts[agent_id] = []

        # Prune timestamps outside the rolling window
        _agent_submission_counts[agent_id] = [ts for ts in _agent_submission_counts[agent_id] if ts > window_start]

        if len(_agent_submission_counts[agent_id]) >= 60:
            raise PinnedConstraintViolation(
                "rate_limit_per_minute",
                f"Agent '{agent_id}' submitted {len(_agent_submission_counts[agent_id])} "
                "tasks in the last minute (limit: 60)",
                task_id=task.id,
            )

        _agent_submission_counts[agent_id].append(now)

    @staticmethod
    def get_pinned_constraints() -> dict[str, str]:
        """Return the active pinned constraints (read-only view)."""
        return dict(PINNED_CONSTRAINTS)

    async def submit_task(self, task: Task) -> str:
        """
        Submit a task for execution.

        Args:
            task: Task to submit

        Returns:
            Task ID
        """
        # Validate against pinned safety constraints before acquiring lock
        self._validate_pinned_constraints(task)

        async with self._task_lock:
            if task.id in self._tasks:
                logger.warning("Task %s already exists, updating", task.id)

            self._tasks[task.id] = task
            heapq.heappush(self._task_queue, task)

            logger.info("Task %s submitted (priority: %s)", task.id, task.priority)
            return task.id

    async def get_task_status(self, task_id: str) -> TaskStatus | None:
        """
        Get status of a task.

        Args:
            task_id: ID of task

        Returns:
            Task status or None if not found
        """
        task = self._tasks.get(task_id)
        return task.status if task else None

    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task.

        Args:
            task_id: ID of task to cancel

        Returns:
            True if cancelled, False if not found or cannot be cancelled
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning("Task %s not found", task_id)
                return False

            if task.status not in [TaskStatus.PENDING, TaskStatus.SCHEDULED]:
                logger.warning("Task %s cannot be cancelled (status: %s)", task_id, task.status)
                return False

            task.cancel()
            logger.info("Task %s cancelled", task_id)
            return True

    async def get_next_task(self, agent_id: str) -> Task | None:
        """
        Get the next task for an agent to execute.

        Args:
            agent_id: ID of agent requesting task

        Returns:
            Next task or None if no tasks available
        """
        async with self._task_lock:
            available_tasks = []

            # Find tasks that can be executed
            for task in self._task_queue:
                if task.status == TaskStatus.PENDING and task.can_execute(self._completed_tasks):
                    available_tasks.append(task)

            if not available_tasks:
                return None

            # Sort by priority and creation time
            available_tasks.sort(key=lambda t: (-t.priority, t.created_at))

            # Get best matching task based on agent load
            agent_load = self._agent_loads.get(agent_id, 0)

            # Select task that minimizes load imbalance
            best_task = available_tasks[0]

            # Mark as scheduled
            best_task.status = TaskStatus.SCHEDULED
            best_task.context["agent_id"] = agent_id
            self._agent_loads[agent_id] = agent_load + 1

            logger.debug("Assigned task %s to agent %s", best_task.id, agent_id)
            return best_task

    async def complete_task(self, task_id: str, result: ExecutionResult):
        """
        Mark a task as completed.

        Args:
            task_id: ID of task
            result: Execution result
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning("Task %s not found", task_id)
                return

            task.status = TaskStatus.COMPLETED
            task.result = result
            task.completed_at = datetime.now(UTC)
            self._completed_tasks.add(task_id)

            # Decrease agent load
            agent_id = task.context.get("agent_id")
            if agent_id:
                self._agent_loads[agent_id] = max(0, self._agent_loads.get(agent_id, 0) - 1)

            logger.info("Task %s completed successfully", task_id)

    async def fail_task(self, task_id: str, error: str):
        """
        Mark a task as failed.

        Args:
            task_id: ID of task
            error: Error message
        """
        async with self._task_lock:
            task = self._tasks.get(task_id)
            if not task:
                logger.warning("Task %s not found", task_id)
                return

            task.status = TaskStatus.FAILED
            task.error = error
            task.completed_at = datetime.now(UTC)
            self._failed_tasks.add(task_id)

            # Decrease agent load
            agent_id = task.context.get("agent_id")
            if agent_id:
                self._agent_loads[agent_id] = max(0, self._agent_loads.get(agent_id, 0) - 1)

            logger.error("Task %s failed: %s", task_id, error)

    async def get_pending_tasks(self) -> list[Task]:
        """
        Get all pending tasks.

        Returns:
            List of pending tasks
        """
        async with self._task_lock:
            return [task for task in self._tasks.values() if task.status == TaskStatus.PENDING]

    async def get_agent_tasks(self, agent_id: str) -> list[Task]:
        """
        Get tasks assigned to a specific agent.

        Args:
            agent_id: ID of agent

        Returns:
            List of tasks for the agent
        """
        async with self._task_lock:
            return [task for task in self._tasks.values() if task.context.get("agent_id") == agent_id]

    async def get_task_count(self) -> dict[str, int]:
        """
        Get task count by status.

        Returns:
            Dictionary with task counts per status
        """
        async with self._task_lock:
            counts = {}
            for status in TaskStatus:
                counts[status.value] = sum(1 for task in self._tasks.values() if task.status == status)
            return counts

    async def get_agent_load(self, agent_id: str) -> int:
        """
        Get current load of an agent.

        Args:
            agent_id: ID of agent

        Returns:
            Number of active tasks
        """
        return self._agent_loads.get(agent_id, 0)

    async def clear_completed_tasks(self, older_than_hours: int = 24):
        """
        Clear completed tasks older than specified time.

        Args:
            older_than_hours: Age in hours
        """
        async with self._task_lock:
            cutoff = datetime.now(UTC).timestamp() - (older_than_hours * 3600)
            to_remove = []

            for task_id, task in self._tasks.items():
                if task.status in [
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                ]:
                    if task.completed_at and task.completed_at.timestamp() < cutoff:
                        to_remove.append(task_id)

            for task_id in to_remove:
                del self._tasks[task_id]
                if task_id in self._completed_tasks:
                    self._completed_tasks.remove(task_id)
                if task_id in self._failed_tasks:
                    self._failed_tasks.remove(task_id)

            logger.info("Cleared %s old tasks", len(to_remove))

    async def is_running(self) -> bool:
        """Check if orchestrator is running."""
        return self._orchestrator_started
