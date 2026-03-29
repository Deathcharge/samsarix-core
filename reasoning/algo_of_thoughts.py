"""
Algorithm of Thoughts (AoT) Implementation

Algorithm of Thoughts is an advanced reasoning technique that:
1. Decomposes problems into algorithmic steps
2. Explores multiple solution paths in parallel
3. Uses systematic elimination of invalid paths
4. Converges on optimal solutions through iterative refinement

This is more structured than Tree of Thoughts and provides:
- Better reliability on complex reasoning tasks
- Systematic exploration of solution space
- Reduced hallucination through validation
- Improved performance on math/logic problems

Reference: "Large Language Models are Zero-Shot Reasoners" (2023)
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class ReasoningStepType(Enum):
    """Types of reasoning steps in AoT."""

    DECOMPOSITION = "decomposition"
    EXPLORATION = "exploration"
    VALIDATION = "validation"
    ELIMINATION = "elimination"
    CONVERGENCE = "convergence"


@dataclass
class ReasoningStep:
    """A single step in the algorithmic reasoning process."""

    step_type: ReasoningStepType
    content: str
    confidence: float
    parent_step: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class SolutionPath:
    """A potential solution path through the reasoning process."""

    path_id: str
    steps: list[ReasoningStep]
    confidence: float
    is_valid: bool
    validation_score: float


class AlgorithmOfThoughts:
    """
    Algorithm of Thoughts reasoning engine.

    This implements a systematic, algorithmic approach to problem-solving
    that explores multiple solution paths in parallel and converges on
    the best solution through validation and elimination.
    """

    def __init__(
        self,
        max_paths: int = 5,
        max_depth: int = 4,
        validation_threshold: float = 0.7,
        parallel_exploration: bool = True,
    ):
        """
        Initialize Algorithm of Thoughts engine.

        Args:
            max_paths: Maximum number of solution paths to explore
            max_depth: Maximum depth of reasoning steps
            validation_threshold: Minimum confidence for a path to be considered valid
            parallel_exploration: Whether to explore paths in parallel
        """
        self.max_paths = max_paths
        self.max_depth = max_depth
        self.validation_threshold = validation_threshold
        self.parallel_exploration = parallel_exploration

        self.solution_paths: list[SolutionPath] = []
        self.current_step = 0

        logger.info(
            f"AlgorithmOfThoughts initialized: max_paths={max_paths}, "
            f"max_depth={max_depth}, validation_threshold={validation_threshold}"
        )

    async def reason(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        llm_caller: Callable | None = None,
    ) -> dict[str, Any]:
        """
        Perform algorithmic reasoning on a problem.

        Args:
            problem: The problem to solve
            context: Additional context for the problem
            llm_caller: Optional LLM caller function for generating steps

        Returns:
            Reasoning result with solution and reasoning trace
        """
        context = context or {}
        self.solution_paths = []
        self.current_step = 0

        logger.info("Starting Algorithm of Thoughts reasoning for: %s...", problem[:100])

        # Step 1: Problem Decomposition
        decomposition = await self._decompose_problem(problem, context, llm_caller)

        # Step 2: Initialize solution paths
        initial_paths = await self._initialize_paths(decomposition, llm_caller)
        self.solution_paths = initial_paths

        # Step 3: Explore paths (parallel or sequential)
        if self.parallel_exploration:
            await self._explore_paths_parallel(problem, context, llm_caller)
        else:
            await self._explore_paths_sequential(problem, context, llm_caller)

        # Step 4: Validate all paths
        await self._validate_paths(problem, context, llm_caller)

        # Step 5: Eliminate invalid paths
        await self._eliminate_invalid_paths()

        # Step 6: Converge on best solution
        best_solution = await self._converge_on_solution(problem, context, llm_caller)

        # Build result
        result = {
            "problem": problem,
            "solution": best_solution["content"],
            "confidence": best_solution["confidence"],
            "reasoning_trace": self._build_reasoning_trace(),
            "paths_explored": len(self.solution_paths),
            "valid_paths": sum(1 for p in self.solution_paths if p.is_valid),
            "total_steps": self.current_step,
            "decomposition": decomposition,
            "algorithm": "Algorithm of Thoughts",
            "metadata": {
                "max_paths": self.max_paths,
                "max_depth": self.max_depth,
                "validation_threshold": self.validation_threshold,
                "parallel_exploration": self.parallel_exploration,
            },
        }

        logger.info(
            f"Algorithm of Thoughts completed: explored {len(self.solution_paths)} paths, "
            f"{sum(1 for p in self.solution_paths if p.is_valid)} valid, "
            f"final confidence: {best_solution['confidence']:.2f}"
        )

        return result

    async def _decompose_problem(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ) -> list[str]:
        """
        Decompose the problem into sub-problems or steps.

        Args:
            problem: The problem to decompose
            context: Additional context
            llm_caller: Optional LLM caller

        Returns:
            List of sub-problems or steps
        """
        _decomposition_step = ReasoningStep(
            step_type=ReasoningStepType.DECOMPOSITION,
            content=f"Decomposing problem: {problem}",
            confidence=0.9,
        )
        self.current_step += 1

        # If no LLM caller provided, use simple heuristic decomposition
        if llm_caller is None:
            decomposition = self._simple_decompose(problem)
        else:
            # Use LLM for intelligent decomposition
            prompt = f"""
            Decompose this problem into algorithmic steps:
            {problem}

            Context: {context}

            Return a list of 3-5 clear, sequential steps.
            """
            response = await llm_caller(prompt)
            decomposition = self._parse_decomposition(response)

        return decomposition

    async def _initialize_paths(
        self,
        decomposition: list[str],
        llm_caller: Callable | None,
    ) -> list[SolutionPath]:
        """
        Initialize initial solution paths based on decomposition.

        Args:
            decomposition: Problem decomposition
            llm_caller: Optional LLM caller

        Returns:
            List of initial solution paths
        """
        paths = []

        for i, step in enumerate(decomposition[: self.max_paths]):
            reasoning_step = ReasoningStep(
                step_type=ReasoningStepType.EXPLORATION,
                content=f"Path {i+1}: {step}",
                confidence=0.8,
                metadata={"path_index": i},
            )

            path = SolutionPath(
                path_id=f"path_{i+1}",
                steps=[reasoning_step],
                confidence=0.8,
                is_valid=True,
                validation_score=0.8,
            )
            paths.append(path)

        return paths

    async def _explore_paths_parallel(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ):
        """
        Explore all solution paths in parallel.

        Args:
            problem: The problem being solved
            context: Additional context
            llm_caller: Optional LLM caller
        """
        tasks = []

        for path in self.solution_paths:
            task = self._explore_single_path(path, problem, context, llm_caller)
            tasks.append(task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _explore_paths_sequential(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ):
        """
        Explore all solution paths sequentially.

        Args:
            problem: The problem being solved
            context: Additional context
            llm_caller: Optional LLM caller
        """
        for path in self.solution_paths:
            await self._explore_single_path(path, problem, context, llm_caller)

    async def _explore_single_path(
        self,
        path: SolutionPath,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ):
        """
        Explore a single solution path to max_depth.

        Args:
            path: The solution path to explore
            problem: The problem being solved
            context: Additional context
            llm_caller: Optional LLM caller
        """
        for depth in range(self.max_depth):
            if len(path.steps) >= self.max_depth:
                break

            # Generate next step in the path
            if llm_caller is None:
                step_content = self._generate_step_content(path, depth)
            else:
                step_content = await self._generate_step_with_llm(path, problem, context, depth, llm_caller)

            reasoning_step = ReasoningStep(
                step_type=ReasoningStepType.EXPLORATION,
                content=step_content,
                confidence=0.85 - (depth * 0.1),  # Confidence decreases with depth
                parent_step=path.steps[-1].content if path.steps else None,
            )

            path.steps.append(reasoning_step)
            self.current_step += 1

    async def _validate_paths(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ):
        """
        Validate all solution paths.

        Args:
            problem: The problem being solved
            context: Additional context
            llm_caller: Optional LLM caller
        """
        for path in self.solution_paths:
            if llm_caller is None:
                validation_score = self._simple_validate(path, problem)
            else:
                validation_score = await self._validate_with_llm(path, problem, context, llm_caller)

            path.validation_score = validation_score
            path.is_valid = validation_score >= self.validation_threshold

            # Add validation step
            validation_step = ReasoningStep(
                step_type=ReasoningStepType.VALIDATION,
                content=f"Validated path with score: {validation_score:.2f}",
                confidence=validation_score,
            )
            path.steps.append(validation_step)

    async def _eliminate_invalid_paths(self):
        """
        Eliminate paths that don't meet validation threshold.
        """
        valid_paths = [p for p in self.solution_paths if p.is_valid]
        eliminated_count = len(self.solution_paths) - len(valid_paths)

        logger.info("Eliminated %s invalid paths, kept %s valid paths", eliminated_count, len(valid_paths))

        # Add elimination steps to paths
        for path in self.solution_paths:
            if not path.is_valid:
                elimination_step = ReasoningStep(
                    step_type=ReasoningStepType.ELIMINATION,
                    content=f"Path eliminated (validation score: {path.validation_score:.2f})",
                    confidence=path.validation_score,
                )
                path.steps.append(elimination_step)

        # Keep only valid paths for convergence
        self.solution_paths = valid_paths

    async def _converge_on_solution(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
    ) -> dict[str, Any]:
        """
        Converge on the best solution from valid paths.

        Args:
            problem: The problem being solved
            context: Additional context
            llm_caller: Optional LLM caller

        Returns:
            Best solution with confidence
        """
        if not self.solution_paths:
            # No valid paths, return best effort
            return {
                "content": "Unable to find a valid solution path",
                "confidence": 0.0,
            }

        # Sort paths by validation score
        sorted_paths = sorted(self.solution_paths, key=lambda p: p.validation_score, reverse=True)

        best_path = sorted_paths[0]

        # Generate final solution from best path
        if llm_caller is None:
            final_solution = self._simple_converge(best_path, problem)
        else:
            final_solution = await self._converge_with_llm(best_path, problem, context, llm_caller)

        # Add convergence step
        convergence_step = ReasoningStep(
            step_type=ReasoningStepType.CONVERGENCE,
            content=f"Converged on solution from path: {best_path.path_id}",
            confidence=best_path.validation_score,
        )
        best_path.steps.append(convergence_step)

        return {
            "content": final_solution,
            "confidence": best_path.validation_score,
            "path_id": best_path.path_id,
        }

    def _build_reasoning_trace(self) -> list[dict[str, Any]]:
        """
        Build a reasoning trace from all solution paths.

        Returns:
            List of reasoning steps with metadata
        """
        trace = []

        for path in self.solution_paths:
            for step in path.steps:
                trace.append(
                    {
                        "path_id": path.path_id,
                        "step_type": step.step_type.value,
                        "content": step.content,
                        "confidence": step.confidence,
                        "parent_step": step.parent_step,
                        "metadata": step.metadata,
                    }
                )

        return trace

    # Helper methods for when LLM caller is not provided

    def _simple_decompose(self, problem: str) -> list[str]:
        """Simple problem decomposition without LLM."""
        return [
            "Understand the problem requirements",
            "Identify key constraints and variables",
            "Explore potential solution approaches",
            "Evaluate and select best approach",
            "Implement and verify solution",
        ]

    def _parse_decomposition(self, response: str) -> list[str]:
        """Parse LLM response into decomposition."""
        # Simple parsing - split by newlines and clean up
        lines = response.strip().split("\n")
        return [line.strip().lstrip("- ").strip() for line in lines if line.strip()]

    def _generate_step_content(self, path: SolutionPath, depth: int) -> str:
        """Generate step content without LLM."""
        return f"Step {depth+1} in {path.path_id}: Exploring solution approach"

    async def _generate_step_with_llm(
        self,
        path: SolutionPath,
        problem: str,
        context: dict[str, Any],
        depth: int,
        llm_caller: callable,
    ) -> str:
        """Generate step content using LLM."""
        previous_steps = "\n".join([s.content for s in path.steps[-3:]])

        prompt = f"""
        Problem: {problem}
        Context: {context}

        Previous steps in this path:
        {previous_steps}

        Generate the next reasoning step (step {depth+1}) to continue solving this problem.
        Be specific and actionable.
        """

        return await llm_caller(prompt)

    def _simple_validate(self, path: SolutionPath, problem: str) -> float:
        """Simple validation without LLM."""
        # Base validation on path length and step quality
        base_score = min(1.0, len(path.steps) / self.max_depth)
        return base_score

    async def _validate_with_llm(
        self,
        path: SolutionPath,
        problem: str,
        context: dict[str, Any],
        llm_caller: callable,
    ) -> float:
        """Validate path using LLM."""
        steps_summary = "\n".join([f"- {s.content}" for s in path.steps])

        prompt = f"""
        Problem: {problem}
        Context: {context}

        Proposed solution path:
        {steps_summary}

        Rate this solution path on a scale of 0.0 to 1.0 based on:
        1. Logical coherence
        2. Problem relevance
        3. Feasibility
        4. Completeness

        Return only a number between 0.0 and 1.0.
        """

        response = await llm_caller(prompt)
        try:
            return float(response.strip())
        except (ValueError, AttributeError):
            return 0.5  # Default middle score

    def _simple_converge(self, path: SolutionPath, problem: str) -> str:
        """Simple convergence without LLM."""
        return f"Solution based on {path.path_id}: " + path.steps[-1].content if path.steps else "No solution"

    async def _converge_with_llm(
        self,
        path: SolutionPath,
        problem: str,
        context: dict[str, Any],
        llm_caller: callable,
    ) -> str:
        """Converge on solution using LLM."""
        steps_summary = "\n".join([f"- {s.content}" for s in path.steps])

        prompt = f"""
        Problem: {problem}
        Context: {context}

        Best solution path steps:
        {steps_summary}

        Synthesize these steps into a clear, concise final solution.
        Be specific and actionable.
        """

        return await llm_caller(prompt)


# Convenience function for quick usage
async def reason_with_aot(
    problem: str,
    context: dict[str, Any] | None = None,
    max_paths: int = 5,
    max_depth: int = 4,
    llm_caller: Callable | None = None,
) -> dict[str, Any]:
    """
    Convenience function to reason using Algorithm of Thoughts.

    Args:
        problem: The problem to solve
        context: Additional context
        max_paths: Maximum number of paths to explore
        max_depth: Maximum depth of reasoning
        llm_caller: Optional LLM caller function

    Returns:
        Reasoning result
    """
    aot = AlgorithmOfThoughts(
        max_paths=max_paths,
        max_depth=max_depth,
    )

    return await aot.reason(problem, context, llm_caller)
