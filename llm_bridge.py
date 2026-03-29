"""
Helix Core LLM Integration - Coordination-Aware LLM Routing
============================================================

This module bridges proprietary_llm with helix_core, enabling:
- Coordination-aware model selection
- UCF metrics tracking for all inference calls
- Automatic tier-based model routing
- Integration with agent enhancement system

Part of Helix Core Adapter System v2.0
"""

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

try:
    from ..config.unified_pricing import HelixCoreFeature, Tier, get_feature_cost_multiplier
except (ImportError, ValueError):
    from enum import Enum as _Enum

    class Tier(_Enum):  # type: ignore[no-redef]
        FREE = "free"
        PRO = "pro"
        ENTERPRISE = "enterprise"

    class HelixCoreFeature(_Enum):  # type: ignore[no-redef]
        LLM = "llm"

    def get_feature_cost_multiplier(*a, **kw):
        return 1.0


try:
    from ..proprietary_llm import TORCH_AVAILABLE, HelixInferenceEngine, initialize_helix_llm_engine
except (ImportError, ValueError):
    TORCH_AVAILABLE = False
    HelixInferenceEngine = None  # type: ignore[assignment, misc]
    initialize_helix_llm_engine = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Request for LLM inference with coordination context"""

    prompt: str
    model_preference: str | None = None
    max_tokens: int = 1024
    temperature: float = 0.7
    coordination_context: dict[str, Any] | None = None
    agent_id: str | None = None
    user_tier: Tier = Tier.FREE
    stream: bool = False


@dataclass
class LLMResponse:
    """Response from coordination-aware LLM"""

    content: str
    model_used: str
    coordination_score: float
    ucf_metrics: dict[str, float]
    tokens_used: int
    inference_time_ms: float
    cost_multiplier: float
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class HelixCoreLLMBridge:
    """
    Bridge between helix_core and proprietary_llm.

    Enables coordination-aware LLM routing through the Helix Core
    adapter system, with automatic tier-based access control and
    UCF metrics integration.
    """

    def __init__(self):
        self._engine: HelixInferenceEngine | None = None
        self._initialized = False
        self._model_mapping = {
            Tier.FREE: ["gpt-3.5-turbo", "claude-instant", "grok-3-mini"],
            Tier.STARTER: ["gpt-3.5-turbo", "claude-instant", "gpt-4", "grok-3-mini"],
            Tier.PRO: ["gpt-4", "claude-3-sonnet", "claude-3-opus", "grok-3"],
            Tier.ENTERPRISE: [
                "gpt-4",
                "claude-3-opus",
                "grok-3",
                "helix-proprietary-v1",
            ],
        }

    async def initialize(self) -> bool:
        """Initialize the LLM bridge with proprietary engine"""
        if self._initialized:
            return True

        try:
            if TORCH_AVAILABLE:
                self._engine = await initialize_helix_llm_engine()
            self._initialized = True
            logger.info("🌀 Helix Core LLM Bridge initialized")
            return True
        except Exception as e:
            logger.error("Failed to initialize LLM bridge: %s", e)
            return False

    def get_available_models(self, tier: Tier) -> list[str]:
        """Get models available for a given tier"""
        available = []
        for t in Tier:
            if t.value <= tier.value:
                available.extend(self._model_mapping.get(t, []))
        return list(set(available))

    async def generate(
        self,
        request: LLMRequest,
    ) -> LLMResponse:
        """
        Generate response with coordination-aware routing.

        Routes to appropriate model based on:
        - User tier access
        - Coordination context
        - UCF metrics optimization
        """
        start_time = datetime.now(UTC)

        # Check tier access
        available_models = self.get_available_models(request.user_tier)

        # Select model (prefer user preference if available)
        model = request.model_preference
        if model not in available_models:
            model = available_models[-1]  # Use best available for tier

        # Calculate cost multiplier
        cost_multiplier = get_feature_cost_multiplier(HelixCoreFeature.UCF_MONITORING, request.user_tier)

        # Generate coordination score from context
        coordination_score = await self._calculate_coordination_score(request.prompt, request.coordination_context)

        # Generate UCF metrics
        ucf_metrics = self._generate_ucf_metrics(coordination_score)

        # Perform inference (mock if engine not available)
        if self._engine and TORCH_AVAILABLE:
            content, tokens = await self._inference_with_engine(
                request.prompt, model, request.max_tokens, request.temperature
            )
        else:
            # Fallback to external API routing
            content, tokens = await self._inference_external(
                request.prompt, model, request.max_tokens, request.temperature
            )

        end_time = datetime.now(UTC)
        inference_time = (end_time - start_time).total_seconds() * 1000

        return LLMResponse(
            content=content,
            model_used=model,
            coordination_score=coordination_score,
            ucf_metrics=ucf_metrics,
            tokens_used=tokens,
            inference_time_ms=inference_time,
            cost_multiplier=cost_multiplier,
        )

    async def _calculate_coordination_score(self, prompt: str, context: dict[str, Any] | None) -> float:
        """Calculate coordination score for the request"""
        base_score = 0.5

        # Boost for coordination-related keywords
        coordination_keywords = [
            "coordination",
            "awareness",
            "mindful",
            "presence",
            "ethical",
            "harmony",
            "resonance",
            "transcend",
        ]

        prompt_lower = prompt.lower()
        for keyword in coordination_keywords:
            if keyword in prompt_lower:
                base_score += 0.05

        # Context multiplier
        if context:
            if context.get("cycle_active", False):
                base_score *= 1.2
            if context.get("ucf_level", 0) > 0.7:
                base_score *= 1.1

        return min(base_score, 1.0)

    def _generate_ucf_metrics(self, coordination_score: float) -> dict[str, float]:
        """Generate UCF metrics based on coordination score"""
        return {
            "harmony": coordination_score * 0.9,
            "resilience": coordination_score * 0.85,
            "throughput_flow": coordination_score * 0.95,
            "focus_focus": coordination_score * 0.88,
            "friction_cleansing": coordination_score * 0.8,
            "velocity_acceleration": coordination_score * 0.92,
        }

    async def _inference_with_engine(self, prompt: str, model: str, max_tokens: int, temperature: float) -> tuple:
        """Perform inference with proprietary Helix LLM engine"""
        # Use the Helix proprietary inference engine
        result = await self._engine.generate(prompt=prompt, model=model, max_tokens=max_tokens, temperature=temperature)
        return result.content, result.tokens_used

    async def _inference_external(self, prompt: str, model: str, max_tokens: int, temperature: float) -> tuple:
        """Route inference to external API providers (OpenAI, Anthropic)"""
        import os

        logger.debug("External API routing for model: %s", model)

        # Try Anthropic for Claude models
        if "claude" in model.lower():
            try:
                from anthropic import AsyncAnthropic

                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    client = AsyncAnthropic(api_key=api_key)
                    response = await client.messages.create(
                        model=model,
                        max_tokens=max_tokens,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.content[0].text if response.content else ""
                    tokens = response.usage.input_tokens + response.usage.output_tokens
                    return content, tokens
            except ImportError:
                logger.debug("anthropic package not available, falling back")
            except Exception as e:
                logger.warning("Anthropic API call failed: %s", e)

        # Try xAI for Grok models
        if "grok" in model.lower():
            try:
                from openai import AsyncOpenAI

                api_key = os.getenv("XAI_API_KEY")
                if api_key:
                    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
                    response = await client.chat.completions.create(
                        model=model,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    content = response.choices[0].message.content or ""
                    tokens = (
                        response.usage.total_tokens if response.usage else len(prompt.split()) + len(content.split())
                    )
                    return content, tokens
            except ImportError:
                logger.debug("openai package not available for xAI, falling back")
            except Exception as e:
                logger.warning("xAI API call failed: %s", e)

        # Try OpenAI for GPT models (or as fallback)
        try:
            from openai import AsyncOpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if api_key:
                client = AsyncOpenAI(api_key=api_key)
                # Map model names if needed
                openai_model = model if "gpt" in model.lower() else "gpt-4"
                response = await client.chat.completions.create(
                    model=openai_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                )
                content = response.choices[0].message.content or ""
                tokens = response.usage.total_tokens if response.usage else len(prompt.split()) + len(content.split())
                return content, tokens
        except ImportError:
            logger.debug("openai package not available, falling back")
        except Exception as e:
            logger.warning("OpenAI API call failed: %s", e)

        # Try helix_flow providers as last resort
        try:
            try:
                from apps.backend.helix_flow import AnthropicProvider, LLMConfig, OpenAIProvider, XAIProvider
            except ImportError:
                from helix_flow import AnthropicProvider, LLMConfig, OpenAIProvider, XAIProvider

            config = LLMConfig(model=model, max_tokens=max_tokens, temperature=temperature)

            if "claude" in model.lower() and os.getenv("ANTHROPIC_API_KEY"):
                provider = AnthropicProvider(config=config)
            elif "grok" in model.lower() and os.getenv("XAI_API_KEY"):
                provider = XAIProvider(config=config)
            elif os.getenv("OPENAI_API_KEY"):
                provider = OpenAIProvider(config=config)
            elif os.getenv("XAI_API_KEY"):
                provider = XAIProvider(config=config)
            else:
                raise RuntimeError("No API keys configured")

            response = await provider.generate(prompt)
            return response.content, response.usage.get("total_tokens", 0)
        except ImportError:
            logger.warning("helix_flow LLM providers not available")
        except Exception as e:
            logger.warning("Helix Flow provider fallback failed: %s", e)

        # Final fallback - no API keys configured
        logger.warning("No LLM API keys configured, returning informational response")
        content = (
            "LLM inference unavailable: No API keys configured. "
            "Set OPENAI_API_KEY or ANTHROPIC_API_KEY environment variables to enable AI responses."
        )
        tokens = len(prompt.split()) + len(content.split())
        return content, tokens


# Global bridge instance
_llm_bridge: HelixCoreLLMBridge | None = None


async def get_helix_llm_bridge() -> HelixCoreLLMBridge:
    """Get or create the global LLM bridge instance"""
    global _llm_bridge
    if _llm_bridge is None:
        _llm_bridge = HelixCoreLLMBridge()
        await _llm_bridge.initialize()
    return _llm_bridge


async def generate_with_coordination(
    prompt: str,
    agent_id: str | None = None,
    user_tier: Tier = Tier.FREE,
    coordination_context: dict[str, Any] | None = None,
    **kwargs,
) -> LLMResponse:
    """
    Convenience function for coordination-aware generation.

    Example:
        response = await generate_with_coordination(
            prompt="Explain the nature of coordination",
            agent_id="kael",
            user_tier=Tier.PRO,
            coordination_context={"cycle_active": True}
        )
        logger.info("UCF Harmony: %s", response.ucf_metrics['harmony'])
    """
    bridge = await get_helix_llm_bridge()

    request = LLMRequest(
        prompt=prompt,
        agent_id=agent_id,
        user_tier=user_tier,
        coordination_context=coordination_context,
        **kwargs,
    )

    return await bridge.generate(request)
