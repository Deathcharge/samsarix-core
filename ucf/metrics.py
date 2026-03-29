"""
Helix Core - UCF Metrics

Universal Coordination Field metrics for agent behavior and coordination.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class UCFMetrics:
    """
    Universal Coordination Field Metrics

    These metrics drive agent behavior, task prioritization, and system-wide
    coordination. They represent the cognitive state of agents within the
    collective coordination.

    Attributes:
        velocity: Scale/resolution of coordination (default: 1024)
        harmony: Coherence and balance (0-1, higher is better)
        resilience: Recovery capability (0-1, higher is better)
        throughput: Energy/activation level (0-1, higher is more active)
        focus: Focused attention (0-1, higher is more focused)
        friction: Impediment factors (0-1, lower is better)
        timestamp: When these metrics were last updated
    """

    velocity: float = 1024.0
    harmony: float = 0.85
    resilience: float = 0.90
    throughput: float = 0.80
    focus: float = 0.85
    friction: float = 0.15
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "velocity": self.velocity,
            "harmony": self.harmony,
            "resilience": self.resilience,
            "throughput": self.throughput,
            "focus": self.focus,
            "friction": self.friction,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UCFMetrics":
        """Create from dictionary."""
        data = data.copy()
        if "timestamp" in data and isinstance(data["timestamp"], str):
            data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        return cls(**data)

    def update(self, **kwargs):
        """Update specific metrics."""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.timestamp = datetime.now(UTC)

    def is_healthy(self) -> bool:
        """Check if metrics indicate healthy state."""
        return (
            self.harmony > 0.70
            and self.resilience > 0.75
            and self.throughput > 0.60
            and self.focus > 0.70
            and self.friction < 0.30
        )

    def calculate_score(self) -> float:
        """Calculate overall coordination score."""
        return (
            self.harmony * 0.25
            + self.resilience * 0.25
            + self.throughput * 0.15
            + self.focus * 0.20
            + (1.0 - self.friction) * 0.15
        )

    def adjust_for_success(self, magnitude: float = 0.05):
        """Adjust metrics after successful execution."""
        self.harmony = min(1.0, self.harmony + magnitude * 0.5)
        self.resilience = min(1.0, self.resilience + magnitude * 0.3)
        self.throughput = min(1.0, self.throughput + magnitude * 0.2)
        self.focus = min(1.0, self.focus + magnitude * 0.2)
        self.friction = max(0.0, self.friction - magnitude * 0.4)
        self.timestamp = datetime.now(UTC)

    def adjust_for_failure(self, magnitude: float = 0.05):
        """Adjust metrics after failed execution."""
        self.harmony = max(0.0, self.harmony - magnitude * 0.3)
        self.resilience = max(0.0, self.resilience - magnitude * 0.4)
        self.throughput = max(0.0, self.throughput - magnitude * 0.3)
        self.focus = max(0.0, self.focus - magnitude * 0.2)
        self.friction = min(1.0, self.friction + magnitude * 0.5)
        self.timestamp = datetime.now(UTC)

    def reset_to_baseline(self, baseline: "UCFMetrics"):
        """Reset metrics to baseline values."""
        self.velocity = baseline.velocity
        self.harmony = baseline.harmony
        self.resilience = baseline.resilience
        self.throughput = baseline.throughput
        self.focus = baseline.focus
        self.friction = baseline.friction
        self.timestamp = datetime.now(UTC)

    def copy(self) -> "UCFMetrics":
        """Create a copy of the metrics."""
        return UCFMetrics(
            velocity=self.velocity,
            harmony=self.harmony,
            resilience=self.resilience,
            throughput=self.throughput,
            focus=self.focus,
            friction=self.friction,
            timestamp=self.timestamp,
        )
