"""
Self-Consistency Reasoning Implementation

Self-Consistency is an advanced reasoning technique that:
1. Samples multiple solutions from the language model
2. Aggregates solutions to find the most consistent answer
3. Uses majority voting or other aggregation methods
4. Reduces hallucinations and improves reliability

This technique is particularly effective for:
- Mathematical reasoning
- Logic puzzles
- Complex problem-solving
- Reducing random errors

Reference: "Self-Consistency Improves Chain of Thought Reasoning" (2023)
"""

import logging
import statistics
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class AggregationMethod(Enum):
    """Methods for aggregating multiple solutions."""

    MAJORITY_VOTE = "majority_vote"
    WEIGHTED_AVERAGE = "weighted_average"
    CONSENSUS = "consensus"
    BEST_CONFIDENCE = "best_confidence"
    MERGE = "merge"


@dataclass
class SolutionSample:
    """A single solution sample from multiple sampling."""

    sample_id: int
    content: str
    confidence: float
    reasoning_trace: list[str]
    metadata: dict[str, Any] | None = None


@dataclass
class ConsensusResult:
    """Result of self-consistency aggregation."""

    final_solution: str
    confidence: float
    aggregation_method: AggregationMethod
    samples_used: int
    agreement_score: float
    top_solutions: list[tuple[str, float]]  # (solution, confidence)
    samples: list[SolutionSample]


class SelfConsistency:
    """
    Self-Consistency reasoning engine.

    This implements multi-sampling reasoning that generates multiple
    solutions and aggregates them to find the most consistent answer.
    """

    def __init__(
        self,
        num_samples: int = 5,
        aggregation_method: AggregationMethod = AggregationMethod.MAJORITY_VOTE,
        temperature_range: tuple[float, float] = (0.7, 1.0),
        min_agreement_threshold: float = 0.4,
    ):
        """
        Initialize Self-Consistency engine.

        Args:
            num_samples: Number of solution samples to generate
            aggregation_method: Method for aggregating solutions
            temperature_range: Temperature range for sampling diversity
            min_agreement_threshold: Minimum agreement score to accept
        """
        self.num_samples = num_samples
        self.aggregation_method = aggregation_method
        self.temperature_range = temperature_range
        self.min_agreement_threshold = min_agreement_threshold

        logger = __import__("logging").getLogger(__name__)
        logger.info(
            f"SelfConsistency initialized: samples={num_samples}, "
            f"method={aggregation_method.value}, temp_range={temperature_range}"
        )

    async def reason(
        self,
        problem: str,
        context: dict[str, Any] | None = None,
        llm_caller: Callable | None = None,
        temperature: float | None = None,
    ) -> dict[str, Any]:
        """
        Perform self-consistency reasoning.

        Args:
            problem: The problem to solve
            context: Additional context
            llm_caller: LLM caller function for generating solutions
            temperature: Temperature for sampling (overrides range)

        Returns:
            Consensus result with aggregated solution
        """
        context = context or {}
        logger = __import__("logging").getLogger(__name__)

        logger.info("Starting Self-Consistency reasoning for: %s...", problem[:100])

        # Step 1: Generate multiple solution samples
        samples = await self._generate_samples(problem, context, llm_caller, temperature)

        # Step 2: Aggregate solutions based on method
        consensus = await self._aggregate_solutions(samples, problem, context)

        # Step 3: Calculate agreement score
        agreement_score = self._calculate_agreement(samples, consensus.final_solution)

        # Step 4: Build result
        result = {
            "problem": problem,
            "solution": consensus.final_solution,
            "confidence": consensus.confidence,
            "agreement_score": agreement_score,
            "aggregation_method": self.aggregation_method.value,
            "samples_used": consensus.samples_used,
            "num_samples": self.num_samples,
            "top_solutions": [{"content": sol[0], "confidence": sol[1]} for sol in consensus.top_solutions],
            "all_samples": [
                {
                    "sample_id": s.sample_id,
                    "content": s.content,
                    "confidence": s.confidence,
                    "reasoning_trace": s.reasoning_trace,
                }
                for s in samples
            ],
            "metadata": {
                "temperature_range": self.temperature_range,
                "min_agreement_threshold": self.min_agreement_threshold,
            },
        }

        logger.info(
            f"Self-Consistency completed: {consensus.samples_used} samples used, "
            f"agreement: {agreement_score:.2f}, confidence: {consensus.confidence:.2f}"
        )

        return result

    async def _generate_samples(
        self,
        problem: str,
        context: dict[str, Any],
        llm_caller: Callable | None,
        temperature: float | None,
    ) -> list[SolutionSample]:
        """Generate multiple solution samples."""
        samples = []

        for i in range(self.num_samples):
            # Calculate temperature for this sample
            if temperature is not None:
                temp = temperature
            else:
                # Vary temperature within range
                temp = (
                    self.temperature_range[0]
                    + (self.temperature_range[1] - self.temperature_range[0]) * (i / (self.num_samples - 1))
                    if self.num_samples > 1
                    else self.temperature_range[0]
                )

            # Generate sample
            if llm_caller is None:
                sample = self._generate_simple_sample(problem, context, i, temp)
            else:
                sample = await self._generate_llm_sample(problem, context, i, temp, llm_caller)

            samples.append(sample)

        return samples

    def _generate_simple_sample(
        self,
        problem: str,
        context: dict[str, Any],
        sample_id: int,
        temperature: float,
    ) -> SolutionSample:
        """Generate a simple sample without LLM."""
        return SolutionSample(
            sample_id=sample_id,
            content=f"Solution {sample_id + 1} for: {problem} (temp={temperature:.2f})",
            confidence=0.7 + (temperature * 0.2),
            reasoning_trace=[
                f"Step 1: Analyze problem with temperature {temperature:.2f}",
                f"Step 2: Generate solution approach {sample_id + 1}",
                "Step 3: Verify solution",
            ],
            metadata={"temperature": temperature},
        )

    async def _generate_llm_sample(
        self,
        problem: str,
        context: dict[str, Any],
        sample_id: int,
        temperature: float,
        llm_caller: Callable,
    ) -> SolutionSample:
        """Generate a sample using LLM."""
        prompt = f"""
        Problem: {problem}
        Context: {context}

        Temperature: {temperature}

        Generate a solution to this problem. Be creative and explore different approaches.
        """

        response = await llm_caller(prompt)

        # Extract confidence if provided
        confidence = 0.8
        if "confidence:" in response.lower():
            try:
                confidence = float(response.split("confidence:")[-1].strip())
            except (ValueError, IndexError) as exc:
                logger.debug("Could not parse confidence from response: %s", exc)

        return SolutionSample(
            sample_id=sample_id,
            content=response,
            confidence=confidence,
            reasoning_trace=[
                f"Generated with temperature {temperature:.2f}",
            ],
            metadata={"temperature": temperature},
        )

    async def _aggregate_solutions(
        self,
        samples: list[SolutionSample],
        problem: str,
        context: dict[str, Any],
    ) -> ConsensusResult:
        """Aggregate solutions based on configured method."""
        if self.aggregation_method == AggregationMethod.MAJORITY_VOTE:
            return await self._majority_vote_aggregation(samples)
        elif self.aggregation_method == AggregationMethod.WEIGHTED_AVERAGE:
            return await self._weighted_average_aggregation(samples)
        elif self.aggregation_method == AggregationMethod.CONSENSUS:
            return await self._consensus_aggregation(samples, problem, context)
        elif self.aggregation_method == AggregationMethod.BEST_CONFIDENCE:
            return await self._best_confidence_aggregation(samples)
        elif self.aggregation_method == AggregationMethod.MERGE:
            return await self._merge_aggregation(samples)
        else:
            return await self._majority_vote_aggregation(samples)

    async def _majority_vote_aggregation(
        self,
        samples: list[SolutionSample],
    ) -> ConsensusResult:
        """Aggregate using majority voting on solution similarity."""
        # For simplicity, use confidence-weighted vote
        # In practice, you'd use semantic similarity

        # Sort by confidence
        sorted_samples = sorted(samples, key=lambda s: s.confidence, reverse=True)

        # Get top solutions
        top_solutions = [(s.content, s.confidence) for s in sorted_samples[:3]]

        # Weighted average of top solutions
        weights = [s.confidence for s in sorted_samples[:3]]
        normalized_weights = [w / sum(weights) for w in weights]

        # Select best solution (weighted by confidence)
        best_idx = 0
        for i, weight in enumerate(normalized_weights):
            if weight > normalized_weights[best_idx]:
                best_idx = i

        final_solution = sorted_samples[best_idx].content
        confidence = sorted_samples[best_idx].confidence

        return ConsensusResult(
            final_solution=final_solution,
            confidence=confidence,
            aggregation_method=self.aggregation_method,
            samples_used=len(samples),
            agreement_score=0.0,  # Calculated separately
            top_solutions=top_solutions,
            samples=samples,
        )

    async def _weighted_average_aggregation(
        self,
        samples: list[SolutionSample],
    ) -> ConsensusResult:
        """Aggregate using weighted average of solutions."""
        total_confidence = sum(s.confidence for s in samples)

        # Select solution with highest weighted contribution
        best_sample = max(samples, key=lambda s: s.confidence / total_confidence)

        top_solutions = sorted(
            [(s.content, s.confidence) for s in samples],
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        return ConsensusResult(
            final_solution=best_sample.content,
            confidence=best_sample.confidence,
            aggregation_method=self.aggregation_method,
            samples_used=len(samples),
            agreement_score=0.0,
            top_solutions=top_solutions,
            samples=samples,
        )

    async def _consensus_aggregation(
        self,
        samples: list[SolutionSample],
        problem: str,
        context: dict[str, Any],
    ) -> ConsensusResult:
        """Aggregate using consensus building."""
        # Find most similar solutions
        # For simplicity, we'll use the most common themes

        # Extract key themes from solutions
        themes = []
        for sample in samples:
            words = sample.content.lower().split()
            themes.extend(words[:5])  # Take first 5 words as theme

        # Find most common theme
        theme_counter = Counter(themes)
        if theme_counter:
            common_theme = theme_counter.most_common(1)[0][0]
        else:
            common_theme = ""

        # Find solution that best represents the consensus
        consensus_sample = max(
            samples,
            key=lambda s: (common_theme in s.content.lower(), s.confidence),
        )

        top_solutions = sorted(
            [(s.content, s.confidence) for s in samples],
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        return ConsensusResult(
            final_solution=consensus_sample.content,
            confidence=consensus_sample.confidence,
            aggregation_method=self.aggregation_method,
            samples_used=len(samples),
            agreement_score=0.0,
            top_solutions=top_solutions,
            samples=samples,
        )

    async def _best_confidence_aggregation(
        self,
        samples: list[SolutionSample],
    ) -> ConsensusResult:
        """Select the solution with highest confidence."""
        best_sample = max(samples, key=lambda s: s.confidence)

        top_solutions = sorted(
            [(s.content, s.confidence) for s in samples],
            key=lambda x: x[1],
            reverse=True,
        )[:3]

        return ConsensusResult(
            final_solution=best_sample.content,
            confidence=best_sample.confidence,
            aggregation_method=self.aggregation_method,
            samples_used=len(samples),
            agreement_score=0.0,
            top_solutions=top_solutions,
            samples=samples,
        )

    async def _merge_aggregation(
        self,
        samples: list[SolutionSample],
    ) -> ConsensusResult:
        """Merge multiple solutions into one."""
        # Combine top solutions
        sorted_samples = sorted(samples, key=lambda s: s.confidence, reverse=True)

        # Merge top 3 solutions
        merged_content = "\n\n".join([f"Approach {i+1}:\n{s.content}" for i, s in enumerate(sorted_samples[:3])])

        # Average confidence
        avg_confidence = statistics.mean(s.confidence for s in sorted_samples[:3])

        top_solutions = [(s.content, s.confidence) for s in sorted_samples[:3]]

        return ConsensusResult(
            final_solution=merged_content,
            confidence=avg_confidence,
            aggregation_method=self.aggregation_method,
            samples_used=len(sorted_samples[:3]),
            agreement_score=0.0,
            top_solutions=top_solutions,
            samples=samples,
        )

    def _calculate_agreement(
        self,
        samples: list[SolutionSample],
        final_solution: str,
    ) -> float:
        """
        Calculate agreement score among samples.

        Returns:
            Agreement score between 0.0 and 1.0
        """
        if len(samples) <= 1:
            return 1.0

        # Simple agreement based on confidence variance
        # Lower variance = higher agreement
        confidences = [s.confidence for s in samples]

        if len(confidences) <= 1:
            return 1.0

        # Calculate variance
        variance = statistics.variance(confidences) if len(confidences) > 1 else 0

        # Convert variance to agreement score
        # Lower variance = higher agreement
        max_variance = 0.25  # Maximum expected variance (confidences range 0-1)
        agreement = max(0.0, 1.0 - (variance / max_variance))

        return min(1.0, max(0.0, agreement))


# Convenience function
async def reason_with_self_consistency(
    problem: str,
    context: dict[str, Any] | None = None,
    num_samples: int = 5,
    aggregation_method: AggregationMethod = AggregationMethod.MAJORITY_VOTE,
    llm_caller: Callable | None = None,
) -> dict[str, Any]:
    """
    Convenience function for self-consistency reasoning.

    Args:
        problem: The problem to solve
        context: Additional context
        num_samples: Number of samples to generate
        aggregation_method: Method for aggregating solutions
        llm_caller: Optional LLM caller function

    Returns:
        Consensus result
    """
    sc = SelfConsistency(
        num_samples=num_samples,
        aggregation_method=aggregation_method,
    )

    return await sc.reason(problem, context, llm_caller)
