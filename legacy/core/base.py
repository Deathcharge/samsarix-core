"""
Helix Core Base Classes and Interfaces

This module defines the foundational classes and interfaces for the Helix Core
autonomous agent runtime system. All Helix Core components inherit from these
base classes to ensure consistency and interoperability.

Key Components:
- Agent, Task, Message dataclasses
- UCFMetrics with health checking and scoring
- TaskStatus, MessageType, AgentState enums
- ExecutionResult, LoopResult for outcome tracking
- AgentConfig for agent initialization

Version: 1.0 - Helix Core Base Infrastructure
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================


class TaskStatus(str, Enum):
    """Status of a task in the system"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MessageType(str, Enum):
    """Type of message between agents"""

    DIRECT = "direct"
    BROADCAST = "broadcast"
    SYSTEM = "system"
    ERROR = "error"
    STATUS = "status"


class AgentState(str, Enum):
    """Current state of an agent"""

    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"


# ============================================================================
# BASE DATACLASSES
# ============================================================================


@dataclass
class UCFMetrics:
    """
    Universal Coordination Field (UCF) Metrics

    UCF is the core coordination framework that tracks six key metrics:
    - velocity: Vision and foresight capabilities
    - harmony: Balance and emotional resonance
    - resilience: Recovery and adaptability
    - throughput: Vitality and energy
    - focus: Focus and attention
    - friction: Obstacles and challenges (lower is better)

    All metrics range from 0-100, with healthy baseline values around 50.
    """

    velocity: float = 50.0
    harmony: float = 50.0
    resilience: float = 50.0
    throughput: float = 50.0
    focus: float = 50.0
    friction: float = 20.0  # Lower is better

    # History tracking
    history: list[dict[str, Any]] = field(default_factory=list)
    max_history: int = 100

    def to_dict(self) -> dict[str, float]:
        """Convert metrics to dictionary"""
        return {
            "velocity": self.velocity,
            "harmony": self.harmony,
            "resilience": self.resilience,
            "throughput": self.throughput,
            "focus": self.focus,
            "friction": self.friction,
            "score": self.calculate_score(),
            "health": self.check_health(),
        }

    def calculate_score(self) -> float:
        """Calculate overall UCF score"""
        # Weighted average with friction inverted
        positive_avg = (self.velocity + self.harmony + self.resilience + self.throughput + self.focus) / 5.0
        friction_penalty = (100 - self.friction) / 100.0
        return positive_avg * friction_penalty

    def check_health(self) -> str:
        """Check overall health based on metrics"""
        score = self.calculate_score()
        if score >= 70:
            return "excellent"
        elif score >= 50:
            return "good"
        elif score >= 30:
            return "fair"
        else:
            return "poor"

    def adjust(
        self,
        velocity: float = 0.0,
        harmony: float = 0.0,
        resilience: float = 0.0,
        throughput: float = 0.0,
        focus: float = 0.0,
        friction: float = 0.0,
    ):
        """Adjust metrics by given amounts"""
        self.velocity = max(0, min(100, self.velocity + velocity))
        self.harmony = max(0, min(100, self.harmony + harmony))
        self.resilience = max(0, min(100, self.resilience + resilience))
        self.throughput = max(0, min(100, self.throughput + throughput))
        self.focus = max(0, min(100, self.focus + focus))
        self.friction = max(0, min(100, self.friction + friction))

        # Record in history
        self._record_history()

    def _record_history(self):
        """Record current metrics in history"""
        timestamp = datetime.now(UTC)
        entry = {
            "timestamp": timestamp.isoformat(),
            "metrics": self.to_dict(),
        }
        self.history.append(entry)

        # Trim history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history :]

    def get_history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Get metrics history"""
        if limit:
            return self.history[-limit:]
        return self.history


@dataclass
class Agent:
    """Base agent representation"""

    agent_id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"Agent({self.name}, {self.state.value})"


@dataclass
class Task:
    """Base task representation"""

    task_id: str
    name: str
    description: str
    agent_id: str
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    parameters: dict[str, Any] = field(default_factory=dict)
    result: Any | None = None
    error: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def start(self):
        """Mark task as started"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now(UTC)

    def complete(self, result: Any):
        """Mark task as completed with result"""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.completed_at = datetime.now(UTC)

    def fail(self, error: str):
        """Mark task as failed with error"""
        self.status = TaskStatus.FAILED
        self.error = error
        self.completed_at = datetime.now(UTC)

    @property
    def duration(self) -> float | None:
        """Get task duration in seconds"""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class Message:
    """Base message representation"""

    message_id: str
    from_agent: str
    to_agent: str
    content: str
    message_type: MessageType = MessageType.DIRECT
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    reply_to: str | None = None

    def __str__(self) -> str:
        return f"Message({self.from_agent} -> {self.to_agent}: {self.content[:50]}...)"


@dataclass
class Goal:
    """High-level goal representation"""

    goal_id: str
    description: str
    agent_id: str
    sub_goals: list["Goal"] = field(default_factory=list)
    priority: int = 0
    status: TaskStatus = TaskStatus.PENDING
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

    def add_sub_goal(self, sub_goal: "Goal"):
        """Add a sub-goal"""
        sub_goal.goal_id = f"{self.goal_id}_{len(self.sub_goals)}"
        self.sub_goals.append(sub_goal)

    def is_completed(self) -> bool:
        """Check if goal and all sub-goals are completed"""
        if self.status != TaskStatus.COMPLETED:
            return False
        return all(sg.status == TaskStatus.COMPLETED for sg in self.sub_goals)


@dataclass
class ExecutionResult:
    """Result of an execution"""

    success: bool
    result: Any
    execution_time: float
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class LoopResult:
    """Result of an execution loop iteration"""

    iteration: int
    success: bool
    result: Any
    improvements: list[str] = field(default_factory=list)
    reflection: str | None = None
    ucf_metrics: UCFMetrics | None = None
    execution_time: float = 0.0


@dataclass
class AgentConfig:
    """Configuration for agent initialization"""

    agent_id: str
    name: str
    description: str
    capabilities: list[str] = field(default_factory=list)
    max_concurrent_tasks: int = 5
    timeout: float = 300.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "max_concurrent_tasks": self.max_concurrent_tasks,
            "timeout": self.timeout,
            "metadata": self.metadata,
        }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================


def generate_agent_id(name: str) -> str:
    """Generate a unique agent ID from name"""
    import uuid

    return f"{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"


def generate_task_id(name: str) -> str:
    """Generate a unique task ID from name"""
    import uuid

    return f"task_{name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}"


def generate_message_id() -> str:
    """Generate a unique message ID"""
    import uuid

    return f"msg_{uuid.uuid4().hex[:8]}"


def calculate_task_priority(
    base_priority: int = 0,
    urgency: int = 0,
    importance: int = 0,
    dependencies_count: int = 0,
) -> int:
    """
    Calculate task priority based on multiple factors.

    Args:
        base_priority: Base priority (0-100)
        urgency: Urgency level (0-100)
        importance: Importance level (0-100)
        dependencies_count: Number of dependencies (more = lower priority)

    Returns:
        Calculated priority (0-100)
    """
    priority = base_priority + urgency + importance
    dependency_penalty = min(dependencies_count * 5, 50)
    priority -= dependency_penalty
    return max(0, min(100, priority))


# ============================================================================
# VALIDATION
# ============================================================================


def validate_ucf_metrics(metrics: UCFMetrics) -> list[str]:
    """Validate UCF metrics and return list of issues"""
    issues = []

    if metrics.velocity < 0 or metrics.velocity > 100:
        issues.append("velocity must be between 0 and 100")
    if metrics.harmony < 0 or metrics.harmony > 100:
        issues.append("harmony must be between 0 and 100")
    if metrics.resilience < 0 or metrics.resilience > 100:
        issues.append("resilience must be between 0 and 100")
    if metrics.throughput < 0 or metrics.throughput > 100:
        issues.append("throughput must be between 0 and 100")
    if metrics.focus < 0 or metrics.focus > 100:
        issues.append("focus must be between 0 and 100")
    if metrics.friction < 0 or metrics.friction > 100:
        issues.append("friction must be between 0 and 100")

    return issues


def validate_agent_config(config: AgentConfig) -> list[str]:
    """Validate agent configuration and return list of issues"""
    issues = []

    if not config.agent_id:
        issues.append("agent_id is required")
    if not config.name:
        issues.append("name is required")
    if config.max_concurrent_tasks < 1:
        issues.append("max_concurrent_tasks must be at least 1")
    if config.timeout < 0:
        issues.append("timeout cannot be negative")

    return issues


if __name__ == "__main__":
    # Test basic functionality
    metrics = UCFMetrics()
    logger.info("Initial UCF Score: %.2f", metrics.calculate_score())
    logger.info("Health: %s", metrics.check_health())

    metrics.adjust(velocity=10, harmony=5)
    logger.info("After adjustment: %.2f", metrics.calculate_score())

    task = Task(
        task_id=generate_task_id("test"),
        name="Test Task",
        description="A test task",
        agent_id="test_agent",
    )
    task.start()
    task.complete({"result": "success"})
    logger.info("Task duration: %ss", task.duration)

    issues = validate_ucf_metrics(metrics)
    logger.info("Validation issues: %s", issues)
