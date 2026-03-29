"""
Helix Core - Execution Loop

Orchestrates planning, execution, and reflection with Tree of Thoughts reasoning.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from .base import (
    ExecutionResult,
    Goal,
    LoopResult,
    UCFMetrics,
)

logger = logging.getLogger(__name__)


class Plan:
    """Represents a plan for executing a goal."""

    def __init__(self, steps: list[dict[str, Any]], confidence: float = 0.8):
        self.steps = steps
        self.confidence = confidence
        self.created_at = datetime.now(UTC)


class ExecutionLoop:
    """
    Orchestrates planning, execution, and reflection.

    The ExecutionLoop is responsible for:
    - Tree of Thoughts reasoning
    - Goal decomposition
    - Task execution
    - Self-reflection and evaluation
    - Error recovery
    - Learning integration
    """

    def __init__(self):
        self._execution_history: list[dict[str, Any]] = []
        self._max_history = 500
        self._loop_started = False

        logger.info("ExecutionLoop initialized")

    async def start(self):
        """Start the execution loop."""
        if self._loop_started:
            logger.warning("ExecutionLoop already started")
            return

        self._loop_started = True
        logger.info("ExecutionLoop started")

    async def stop(self):
        """Stop the execution loop."""
        if not self._loop_started:
            logger.warning("ExecutionLoop not started")
            return

        self._loop_started = False
        logger.info("ExecutionLoop stopped")

    async def plan(self, goal: Goal, ucf_context: UCFMetrics) -> Plan:
        """
        Create a plan for achieving a goal.

        Uses Tree of Thoughts reasoning to explore multiple paths
        and select the best approach.

        Args:
            goal: Goal to achieve
            ucf_context: UCF metrics for context

        Returns:
            Execution plan
        """
        logger.info("Planning for goal: %s", goal.description)

        # Generate multiple thought paths
        thought_paths = await self._generate_thought_paths(goal, ucf_context)

        # Evaluate each path
        evaluated_paths = []
        for path in thought_paths:
            score = await self._evaluate_path(path, ucf_context)
            evaluated_paths.append((path, score))

        # Select best path
        best_path, best_score = max(evaluated_paths, key=lambda x: x[1])

        # Convert to plan steps
        steps = [{"description": step, "type": "action", "estimated_time": 10} for step in best_path]

        plan = Plan(steps=steps, confidence=best_score)

        logger.info("Plan created with %s steps, confidence: %.2f", len(steps), best_score)
        return plan

    async def _generate_thought_paths(self, goal: Goal, ucf_context: UCFMetrics) -> list[list[str]]:
        """
        Generate multiple thought paths using Tree of Thoughts.

        Args:
            goal: Goal to plan for
            ucf_context: UCF metrics

        Returns:
            List of thought paths
        """
        # Simple implementation - decompose goal into sub-goals
        if goal.sub_goals:
            return [[sub.description for sub in goal.sub_goals]]

        # Auto-decompose based on goal description
        return [
            [
                f"Analyze requirements for: {goal.description}",
                f"Identify key components for: {goal.description}",
                f"Execute implementation of: {goal.description}",
                f"Verify results for: {goal.description}",
            ]
        ]

    async def _evaluate_path(self, path: list[str], ucf_context: UCFMetrics) -> float:
        """
        Evaluate a thought path based on UCF metrics.

        Args:
            path: Thought path to evaluate
            ucf_context: UCF metrics

        Returns:
            Score (0-1)
        """
        # Simple scoring based on UCF metrics
        base_score = 0.7

        # Harmony increases confidence
        base_score += ucf_context.harmony * 0.15

        # Focus (focus) increases confidence
        base_score += ucf_context.focus * 0.1

        # Resilience increases confidence
        base_score += ucf_context.resilience * 0.05

        # Throughput (energy) increases confidence
        base_score += ucf_context.throughput * 0.05

        # Friction (impediment) decreases confidence
        base_score -= ucf_context.friction * 0.1

        return min(max(base_score, 0.0), 1.0)

    async def execute(self, plan: Plan, executor: Any, ucf_context: UCFMetrics) -> ExecutionResult:
        """
        Execute a plan.

        Args:
            plan: Plan to execute
            executor: Executor function
            ucf_context: UCF metrics

        Returns:
            Execution result
        """
        logger.info("Executing plan with %s steps", len(plan.steps))

        results = []
        errors = []

        for i, step in enumerate(plan.steps):
            logger.info("Executing step %s/%s: %s", i + 1, len(plan.steps), step["description"])

            try:
                # Execute step
                step_result = await executor(step)
                results.append(step_result)

                # Update UCF based on progress
                ucf_context.throughput += 0.02
                ucf_context.friction -= 0.01

            except Exception as e:
                error_msg = f"Step {i + 1} failed: {e!s}"
                errors.append(error_msg)
                logger.error(error_msg, exc_info=True)

                # Update UCF on error
                ucf_context.friction += 0.1
                ucf_context.throughput -= 0.05

                # Continue execution if possible
                continue

        success = len(errors) == 0

        return ExecutionResult(
            success=success,
            output=results if success else None,
            error="; ".join(errors) if errors else None,
            metrics={
                "steps_completed": len(results),
                "steps_failed": len(errors),
                "total_steps": len(plan.steps),
            },
            ucf_metrics=ucf_context,
        )

    async def reflect(self, result: ExecutionResult, original_goal: str, ucf_context: UCFMetrics) -> str:
        """
        Reflect on execution outcome.

        Args:
            result: Execution result
            original_goal: Original goal description
            ucf_context: UCF metrics

        Returns:
            Reflection text
        """
        logger.info("Reflecting on execution outcome")

        if result.success:
            reflection = f"Successfully achieved goal: {original_goal}. "
            reflection += f"Completed {result.metrics.get('steps_completed', 0)} steps. "
            reflection += "Key learnings: Efficient execution, positive UCF trajectory."

            # Update UCF on success
            ucf_context.harmony += 0.05
            ucf_context.resilience += 0.03
            ucf_context.focus += 0.02

        else:
            reflection = f"Failed to achieve goal: {original_goal}. "
            reflection += f"Error: {result.error}. "
            reflection += "Analysis: Need to improve error handling and recovery mechanisms."

            # Update UCF on failure
            ucf_context.friction += 0.05
            ucf_context.resilience -= 0.02

        logger.info("Reflection: %s", reflection)
        return reflection

    async def decompose_goal(self, goal: Goal) -> list[Goal]:
        """
        Decompose a goal into sub-goals.

        Args:
            goal: Goal to decompose

        Returns:
            List of sub-goals
        """
        logger.info("Decomposing goal: %s", goal.description)

        # Simple decomposition based on goal complexity
        sub_goal_descriptions = [
            "Analyze requirements",
            "Design solution",
            "Implement solution",
            "Test and verify",
            "Deploy and monitor",
        ]

        sub_goals = goal.decompose(sub_goal_descriptions)

        logger.info("Decomposed into %s sub-goals", len(sub_goals))
        return sub_goals

    async def evaluate_outcome(self, outcome: ExecutionResult, expected_result: Any) -> float:
        """
        Evaluate the quality of an outcome.

        Args:
            outcome: Execution result
            expected_result: Expected result

        Returns:
            Quality score (0-1)
        """
        if not outcome.success:
            return 0.0

        # Simple comparison
        if outcome.output == expected_result:
            return 1.0

        # Partial match based on UCF
        base_score = 0.5
        base_score += outcome.ucf_metrics.harmony * 0.3
        base_score += outcome.ucf_metrics.resilience * 0.2

        return min(max(base_score, 0.0), 1.0)

    async def run_cognitive_loop(
        self,
        goal: Goal,
        executor: Any,
        max_iterations: int = 10,
        reflection_interval: int = 3,
        ucf_context: UCFMetrics | None = None,
    ) -> LoopResult:
        """
        Run a full cognitive loop with planning, execution, and reflection.

        Args:
            goal: Goal to achieve
            executor: Executor function
            max_iterations: Maximum iterations
            reflection_interval: Iterations between reflections
            ucf_context: Initial UCF metrics

        Returns:
            Loop result
        """
        start_time = datetime.now(UTC)
        ucf_context = ucf_context or UCFMetrics()
        ucf_trajectory = []
        reflections = []

        logger.info("Starting cognitive loop for goal: %s", goal.description)

        for iteration in range(max_iterations):
            # Track UCF
            ucf_trajectory.append(UCFMetrics(**ucf_context.to_dict()))

            # Plan
            plan = await self.plan(goal, ucf_context)

            # Execute
            result = await self.execute(plan, executor, ucf_context)

            # Reflect at intervals or on failure
            if iteration % reflection_interval == 0 or not result.success:
                reflection = await self.reflect(result, goal.description, ucf_context)
                reflections.append(reflection)

            # Check success
            if result.success:
                logger.info("Goal achieved in %s iterations", iteration + 1)
                break

            # Update goal for next iteration based on reflection
            if not result.success:
                logger.info("Iteration %s failed, retrying...", iteration + 1)
                # Adjust goal based on reflection
                continue

        total_time = (datetime.now(UTC) - start_time).total_seconds()

        return LoopResult(
            success=result.success,
            final_result=result.output,
            iterations=iteration + 1,
            reflections=reflections,
            total_time=total_time,
            ucf_trajectory=ucf_trajectory,
        )

    async def get_execution_history(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Get execution history.

        Args:
            limit: Maximum number of entries

        Returns:
            List of execution entries
        """
        return self._execution_history[-limit:]

    async def is_running(self) -> bool:
        """Check if execution loop is running."""
        return self._loop_started
