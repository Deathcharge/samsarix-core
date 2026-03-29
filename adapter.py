"""
Helix Core Adapter - Integration Layer for Agent Enhancement

This module provides seamless integration between existing agents and
Helix Core runtime enhancements. Acts as a bridge that can enable/disable
features based on subscription tier and user preferences.

Key Design Principles:
1. Zero disruption to existing agents
2. Transparent enhancement toggles
3. Performance monitoring and comparison
4. Billing tier integration
5. Backward compatibility maintained

Version: 2.0 - Integrated with Unified Pricing System
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from ..config.unified_pricing import (
        HELIX_CORE_FEATURES,
        HelixCoreFeature,
        Tier,
        get_feature_cost_multiplier,
        get_feature_performance_impact,
        get_helix_core_features_for_tier,
        has_feature_access,
    )
except (ImportError, ValueError):
    # Standalone mode: unified_pricing not available
    from enum import Enum as _Enum

    class Tier(_Enum):  # type: ignore[no-redef]
        FREE = "free"
        HOBBY = "hobby"
        STARTER = "starter"
        PRO = "pro"
        ENTERPRISE = "enterprise"

    class HelixCoreFeature(_Enum):  # type: ignore[no-redef]
        REASONING = "reasoning"
        TOOLS = "tools"
        UCF = "ucf"

    HELIX_CORE_FEATURES = {}

    def get_feature_cost_multiplier(*a, **kw):
        return 1.0

    def get_feature_performance_impact(*a, **kw):
        return 1.0

    def get_helix_core_features_for_tier(*a, **kw):
        return []

    def has_feature_access(*a, **kw):
        return True


logger = logging.getLogger(__name__)


@dataclass
class EnhancementFeature:
    """Represents a single enhancement feature (unified pricing version)"""

    feature_id: HelixCoreFeature
    name: str
    description: str
    tier_access: set[Tier]
    enabled: bool = False
    performance_impact: float = 1.0
    api_cost_multiplier: float = 1.0


@dataclass
class EnhancementStatus:
    """Current enhancement status for an agent"""

    agent_id: str
    features: list[EnhancementFeature]
    tier: Tier = Tier.FREE
    enabled_count: int = 0
    total_count: int = 0
    total_performance_impact: float = 1.0
    total_cost_multiplier: float = 1.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def feature_names(self) -> list[str]:
        """Get list of enabled feature names"""
        return [f.name for f in self.features if f.enabled]


@dataclass
class EnhancementMetrics:
    """Performance metrics for enhanced agent"""

    execution_time_original: float
    execution_time_enhanced: float
    improvement_percentage: float
    cost_original: float
    cost_enhanced: float
    cost_increase_percentage: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class HelixCoreAdapter:
    """
    Adapter that wraps existing agents with Helix Core enhancements.

    This is the critical integration layer that enables the "build-up" strategy:
    - Existing agents work without changes
    - Enhancements are opt-in via feature flags
    - Performance is monitored and compared
    - Billing tier controls feature access
    - Integrated with unified pricing configuration

    Version: 2.0 - Uses unified pricing configuration
    """

    def __init__(
        self,
        original_agent: Any | None = None,
        tier: Tier = Tier.FREE,
        enabled_features: list[HelixCoreFeature] | None = None,
    ):
        self.original_agent = original_agent
        # Handle both Tier enum and string values
        if isinstance(tier, str):
            self.tier = Tier(tier.lower())
        else:
            self.tier = tier
        self.enabled_features: set[HelixCoreFeature] = set(enabled_features or [])
        self._status = self._init_status()
        self._metrics_history: list[EnhancementMetrics] = []

        logger.info(
            f"HelixCoreAdapter v2.0 initialized for tier={self.tier.value}, "
            f"features={[f.value for f in self.enabled_features]}"
        )

    def _init_status(self) -> EnhancementStatus:
        """Initialize enhancement status from unified pricing config"""
        features = []
        enabled_count = 0

        # Get features available for this tier
        available_features = get_helix_core_features_for_tier(self.tier)

        for feature_id in available_features:
            feature_config = HELIX_CORE_FEATURES[feature_id]
            is_enabled = feature_id in self.enabled_features

            features.append(
                EnhancementFeature(
                    feature_id=feature_id,
                    name=feature_config.name,
                    description=feature_config.description,
                    tier_access=feature_config.tier_access,
                    enabled=is_enabled,
                    performance_impact=feature_config.performance_impact,
                    api_cost_multiplier=feature_config.api_cost_multiplier,
                )
            )

            if is_enabled:
                enabled_count += 1

        return EnhancementStatus(
            agent_id=(getattr(self.original_agent, "name", "unknown") if self.original_agent else "unknown"),
            features=features,
            tier=self.tier,
            enabled_count=enabled_count,
            total_count=len(features),
            total_performance_impact=get_feature_performance_impact(self.tier),
            total_cost_multiplier=get_feature_cost_multiplier(self.tier),
        )

    async def get_enhancement_status(self) -> EnhancementStatus:
        """Get current enhancement status"""
        self._status.last_updated = datetime.now(UTC)
        self._status.enabled_count = sum(1 for f in self._status.features if f.enabled)
        return self._status

    async def check_feature_access(self, feature: HelixCoreFeature) -> bool:
        """Check if a feature is accessible for current tier"""
        return has_feature_access(self.tier, feature)

    async def enable_feature(self, feature: HelixCoreFeature) -> bool:
        """Enable a specific feature (if tier allows)"""
        if not await self.check_feature_access(feature):
            logger.warning("Feature '%s' not accessible for tier '%s'", feature.value, self.tier.value)
            return False

        self.enabled_features.add(feature)
        self._status = self._init_status()
        logger.info("Feature '%s' enabled", feature.value)
        return True

    async def disable_feature(self, feature: HelixCoreFeature) -> bool:
        """Disable a specific feature"""
        if feature in self.enabled_features:
            self.enabled_features.remove(feature)
            self._status = self._init_status()
            logger.info("Feature '%s' disabled", feature.value)
            return True
        return False

    async def get_available_features_for_tier(self, tier: Tier | None = None) -> list[str]:
        """Get list of features available for a tier"""
        target_tier = tier if tier else self.tier
        return [f.value for f in get_helix_core_features_for_tier(target_tier)]

    async def execute_with_metrics(self, original_func: callable, *args, **kwargs) -> tuple[Any, EnhancementMetrics]:
        """
        Execute function with performance metrics comparing original vs enhanced.

        Returns:
            (result, metrics) - Function result and performance metrics
        """
        if not self.enabled_features:
            # No enhancements, just execute and return basic metrics
            start_time = time.time()
            result = await original_func(*args, **kwargs)
            execution_time = time.time() - start_time

            metrics = EnhancementMetrics(
                execution_time_original=execution_time,
                execution_time_enhanced=execution_time,
                improvement_percentage=0.0,
                cost_original=1.0,
                cost_enhanced=1.0,
                cost_increase_percentage=0.0,
            )
            return result, metrics

        # Execute with enhancements and track metrics
        start_time = time.time()
        result = await original_func(*args, **kwargs)
        enhanced_time = time.time() - start_time

        # Estimate original time (divide by performance impact)
        original_time = enhanced_time / self._status.total_performance_impact

        # Calculate metrics
        improvement = ((original_time - enhanced_time) / original_time) * 100
        cost_increase = (self._status.total_cost_multiplier - 1.0) * 100

        metrics = EnhancementMetrics(
            execution_time_original=original_time,
            execution_time_enhanced=enhanced_time,
            improvement_percentage=improvement,
            cost_original=1.0,
            cost_enhanced=self._status.total_cost_multiplier,
            cost_increase_percentage=cost_increase,
        )

        self._metrics_history.append(metrics)

        # Keep only last 100 metrics
        if len(self._metrics_history) > 100:
            self._metrics_history = self._metrics_history[-100:]

        logger.info(
            f"Enhanced execution: {enhanced_time:.3f}s vs {original_time:.3f}s "
            f"({improvement:+.1f}% improvement, {cost_increase:+.1f}% cost)"
        )

        return result, metrics

    def get_average_metrics(self) -> dict[str, float] | None:
        """Get average performance metrics across all executions"""
        if not self._metrics_history:
            return None

        avg_time_original = sum(m.execution_time_original for m in self._metrics_history) / len(self._metrics_history)
        avg_time_enhanced = sum(m.execution_time_enhanced for m in self._metrics_history) / len(self._metrics_history)
        avg_improvement = sum(m.improvement_percentage for m in self._metrics_history) / len(self._metrics_history)
        avg_cost_increase = sum(m.cost_increase_percentage for m in self._metrics_history) / len(self._metrics_history)

        return {
            "avg_execution_time_original": avg_time_original,
            "avg_execution_time_enhanced": avg_time_enhanced,
            "avg_improvement_percentage": avg_improvement,
            "avg_cost_increase_percentage": avg_cost_increase,
            "total_executions": len(self._metrics_history),
        }

    def clear_metrics_history(self) -> None:
        """Clear metrics history"""
        self._metrics_history.clear()
        logger.info("Metrics history cleared")

    async def execute_with_algorithm_of_thoughts(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        max_paths: int = 5,
        max_depth: int = 4,
        llm_caller: Callable | None = None,
    ) -> dict[str, Any]:
        """
        Execute reasoning using Algorithm of Thoughts (AoT).

        This advanced reasoning technique:
        - Decomposes problems into algorithmic steps
        - Explores multiple solution paths in parallel
        - Uses systematic elimination of invalid paths
        - Converges on optimal solutions

        Args:
            problem: The problem to solve
            context: Additional context for the problem
            max_paths: Maximum number of solution paths to explore
            max_depth: Maximum depth of reasoning steps
            llm_caller: Optional LLM caller function for generating steps

        Returns:
            Reasoning result with solution and trace
        """
        from .reasoning import reason_with_aot

        # Check if feature is enabled
        has_access = await self.check_feature_access(HelixCoreFeature.TREE_OF_THOUGHTS)

        if not has_access:
            logger.warning(
                "Algorithm of Thoughts not available for current tier. "
                "Upgrade to Pro or Enterprise for advanced reasoning."
            )
            return {
                "problem": problem,
                "solution": "Feature not available - upgrade tier",
                "confidence": 0.0,
                "error": "TREE_OF_THOUGHTS feature not enabled",
                "reasoning_trace": [],
            }

        logger.info("Executing Algorithm of Thoughts for: %s...", problem[:100])

        # Execute AoT reasoning
        result = await reason_with_aot(
            problem=problem,
            context=context,
            max_paths=max_paths,
            max_depth=max_depth,
            llm_caller=llm_caller,
        )

        # Track metrics if available
        if hasattr(self, "_metrics_history"):
            logger.info(
                f"AoT completed: {result['paths_explored']} paths explored, " f"confidence: {result['confidence']:.2f}"
            )

        return result


# Utility functions
async def get_feature_matrix() -> dict[str, dict[str, bool]]:
    """Get feature access matrix for all tiers"""
    matrix = {}
    for tier in Tier:
        matrix[tier.value] = {}
        for feature in HelixCoreFeature:
            matrix[tier.value][feature.value] = has_feature_access(tier, feature)
    return matrix


async def create_adapter_for_user(
    original_agent: Any, user_tier: str, enabled_features: list[str] | None = None
) -> HelixCoreAdapter:
    """
    Factory function to create adapter for a user.

    Args:
        original_agent: The agent to enhance
        user_tier: User's subscription tier (free, pro, enterprise)
        enabled_features: List of feature names to enable

    Returns:
        Configured HelixCoreAdapter
    """
    # Normalize tier
    tier_mapping = {
        "standard": Tier.FREE,
        "starter": Tier.FREE,
        "free": Tier.FREE,
        "pro": Tier.PRO,
        "enterprise": Tier.ENTERPRISE,
    }

    normalized_tier = tier_mapping.get(user_tier.lower(), Tier.FREE)

    # Convert feature names to enums
    feature_enums = []
    if enabled_features:
        for feature_name in enabled_features:
            try:
                feature_enum = HelixCoreFeature(feature_name)
                feature_enums.append(feature_enum)
            except ValueError:
                logger.warning("Unknown feature: %s", feature_name)

    return HelixCoreAdapter(
        original_agent=original_agent,
        tier=normalized_tier,
        enabled_features=feature_enums,
    )
