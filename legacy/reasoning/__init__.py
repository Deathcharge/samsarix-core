"""
Helix Core Reasoning Module

This module provides advanced reasoning capabilities for Helix agents,
including Algorithm of Thoughts, Self-Consistency, and Reflexion loops.

These reasoning techniques enable agents to:
- Solve complex problems systematically
- Explore multiple solution paths
- Validate and improve their reasoning
- Reduce hallucinations and errors

Components:
- AlgorithmOfThoughts: Systematic, algorithmic reasoning
- SelfConsistency: Multi-sampling for reliable solutions
- Reflexion: Self-reflection and improvement
"""

from .algo_of_thoughts import (
    AlgorithmOfThoughts,
    ReasoningStep,
    ReasoningStepType,
    SolutionPath,
    reason_with_aot,
)
from .self_consistency import (
    AggregationMethod,
    ConsensusResult,
    SelfConsistency,
    SolutionSample,
    reason_with_self_consistency,
)

__all__ = [
    # Algorithm of Thoughts
    "AlgorithmOfThoughts",
    "ReasoningStepType",
    "ReasoningStep",
    "SolutionPath",
    "reason_with_aot",
    # Self-Consistency
    "SelfConsistency",
    "AggregationMethod",
    "SolutionSample",
    "ConsensusResult",
    "reason_with_self_consistency",
]
