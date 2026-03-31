"""
🌀 Helix Unified LLM Service
=============================

Single gateway for ALL LLM calls across the platform.
Wraps helix_flow providers (OpenAI, Anthropic, xAI, Local)
so that setting an API key once makes it available everywhere.

Usage:
    from apps.backend.services.unified_llm import unified_llm

    # Simple generation (auto-selects best available provider)
    text = await unified_llm.generate("Explain system computing")

    # Chat with messages
    text = await unified_llm.chat([
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
    ])

    # Specify provider/model
    text = await unified_llm.chat(messages, model="grok-3-mini")
    text = await unified_llm.chat(messages, provider="anthropic")

    # Use a user's BYOT key (falls back to platform key if none set)
    text = await unified_llm.chat(messages, user_id="user-123")

    # Get response with metadata (tokens, cost, model used)
    resp = await unified_llm.chat_with_metadata(messages)
    logger.info(resp.content, resp.model, resp.usage)

Author: Helix Collective
Version: 1.0.0
"""

import hashlib
import json as _json
import logging
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# Import retry decorator for resilient LLM calls
try:
    from apps.backend.core.resilience import retry_with_backoff
except ImportError:

    def retry_with_backoff(**_kw):
        def _noop(fn):
            return fn

        return _noop


# Import helix_flow providers
try:
    from apps.backend.helix_flow.llm import (
        AnthropicProvider,
        LLMConfig,
        LLMResponse as FlowLLMResponse,
        OpenAIProvider,
        XAIProvider,
    )

    HELIX_FLOW_AVAILABLE = True
except ImportError:
    HELIX_FLOW_AVAILABLE = False
    logger.warning("helix_flow not available — unified LLM will use direct SDK fallback")


# ============================================================================
# RESPONSE DATACLASS
# ============================================================================


@dataclass
class UnifiedLLMResponse:
    """Response from any LLM provider with metadata"""

    content: str
    model: str
    provider: str
    usage: dict[str, int] = field(default_factory=dict)
    finish_reason: str = "stop"
    error: str | None = None
    tool_calls: list[Any] | None = None

    @property
    def total_tokens(self) -> int:
        return self.usage.get("total_tokens", 0)


# ============================================================================
# HELIX NATIVE ENGINE PROVIDER
# ============================================================================


class _HelixEngineProvider:
    """Thin HTTP wrapper around the helix-llm-engine Railway service.

    Conforms to the same .chat() / .generate() interface used by helix_flow
    providers so it can be dropped into unified_llm._providers seamlessly.
    Calls POST {engine_url}/llm/internal/generate (internal secret-auth endpoint).
    Falls back to Qwen 2.5 GGUF on the engine service; eventually uses the
    trained custom model as weights become available.
    """

    def __init__(self, engine_url: str) -> None:
        self._engine_url = engine_url.rstrip("/")
        # Internal endpoint bypasses user JWT — authenticated by shared secret
        self._inference_url = f"{self._engine_url}/llm/internal/generate"
        self._secret = os.environ.get("HELIX_INTERNAL_SECRET", "")

    async def chat(self, messages: list, max_tokens: int = 1024, **kwargs) -> str:
        """Send a chat request to the Helix LLM engine and return the text."""
        import aiohttp

        # Convert messages list to a single prompt string (engine expects a prompt)
        prompt = "\n".join(f"{m.get('role', 'user').upper()}: {m.get('content', '')}" for m in messages)
        payload = {
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": kwargs.get("temperature", 0.7),
        }
        headers = {"X-Internal-Secret": self._secret} if self._secret else {}
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.post(
                    self._inference_url,
                    json=payload,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=60),
                ) as resp,
            ):
                if resp.status != 200:
                    raise RuntimeError(f"Helix engine returned {resp.status}")
                data = await resp.json()
                return data.get("text") or data.get("generated_text") or str(data)
        except Exception as exc:
            raise RuntimeError(f"Helix engine call failed: {exc}") from exc

    async def generate(self, prompt: str, max_tokens: int = 1024, **kwargs) -> str:
        """Single-prompt generation via the Helix LLM engine."""
        return await self.chat([{"role": "user", "content": prompt}], max_tokens=max_tokens, **kwargs)

    async def health(self) -> dict:
        """Check the engine's /llm/health endpoint."""
        import aiohttp

        try:
            async with (
                aiohttp.ClientSession() as session,
                session.get(
                    f"{self._engine_url}/llm/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp,
            ):
                return await resp.json()
        except Exception as exc:
            return {"status": "unreachable", "error": str(exc)}


# ============================================================================
# PROVIDER REGISTRY
# ============================================================================

# Maps provider name -> (env_var_for_key, default_model, provider_class_factory)
PROVIDER_REGISTRY = {
    "anthropic": {
        "env_var": "ANTHROPIC_API_KEY",
        "default_model": "claude-sonnet-4-5",
        "models": [
            "claude-sonnet-4-5",
            "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
            "claude-3-sonnet-20240229",
            "claude-3-haiku-20240307",
            "claude-instant",
        ],
    },
    "openai": {
        "env_var": "OPENAI_API_KEY",
        "default_model": "gpt-4-turbo",
        "models": [
            "gpt-4-turbo",
            "gpt-4-turbo-2024-04-09",
            "gpt-4",
            "gpt-4-1106-preview",
            "gpt-3.5-turbo",
            "gpt-3.5-turbo-0125",
        ],
    },
    "xai": {
        "env_var": "XAI_API_KEY",
        "default_model": "grok-3-mini",
        "models": [
            "grok-3",
            "grok-3-mini",
            "grok-beta",
        ],
    },
    "perplexity": {
        "env_var": "PERPLEXITY_API_KEY",
        "default_model": "llama-3-sonar-large-32k-online",
        "models": [
            "llama-3-sonar-large-32k-online",
            "sonar",
        ],
    },
    "google": {
        "env_var": "GOOGLE_AI_KEY",
        "default_model": "gemini-2.0-flash",
        "models": [
            "gemini-2.0-flash",
            "gemini-pro",
        ],
    },
    "local": {
        "env_var": "HELIX_LOCAL_MODEL",  # Model name or path
        "default_model": "helix-ai",
        "models": [
            "helix-ai",
            "phi-3-mini",
            "qwen2.5-1.5b",
            "tinyllama",
        ],
    },
    "openrouter": {
        "env_var": "OPENROUTER_API_KEY",
        "default_model": "anthropic/claude-sonnet-4-5",
        "models": [
            # OpenRouter proxies 300+ models — these are the most popular
            "anthropic/claude-sonnet-4-5",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "openai/gpt-4o",
            "openai/gpt-4o-mini",
            "openai/gpt-4-turbo",
            "google/gemini-2.0-flash-exp",
            "google/gemini-pro-1.5",
            "meta-llama/llama-3.1-405b-instruct",
            "meta-llama/llama-3.1-70b-instruct",
            "mistralai/mistral-large",
            "mistralai/mixtral-8x22b-instruct",
            "deepseek/deepseek-r1",
            "deepseek/deepseek-chat",
            "qwen/qwen-2.5-72b-instruct",
            "cohere/command-r-plus",
            # Free models for free-tier routing
            "minimax/minimax-m2.5",
            "arcee-ai/trinity-large-preview:free",
            "kwaipilot/kat-coder-pro:free",
            "nvidia/nemotron-3-super",
            "google/gemini-2.0-flash-exp:free",
            "mistralai/mistral-7b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "microsoft/phi-4:free",
        ],
    },
    "groq": {
        "env_var": "GROQ_API_KEY",
        "default_model": "llama-3.3-70b-versatile",
        "models": [
            "llama-3.3-70b-versatile",
            "llama-3.1-8b-instant",
            "mixtral-8x7b-32768",
            "gemma2-9b-it",
        ],
    },
    "mistral": {
        "env_var": "MISTRAL_API_KEY",
        "default_model": "mistral-small-latest",
        "models": [
            "mistral-small-latest",
            "mistral-medium-latest",
            "mistral-large-latest",
        ],
    },
    "nvidia_nim": {
        "env_var": "NVIDIA_NIM_API_KEY",
        "default_model": "nvidia/llama-3.1-nemotron-70b-instruct",
        "models": [
            "nvidia/llama-3.1-nemotron-70b-instruct",
        ],
    },
    "minimax": {
        "env_var": "MINIMAX_API_KEY",
        "default_model": "minimax-m2.5",
        "models": ["minimax-m2.5"],
    },
    "cohere": {
        "env_var": "COHERE_API_KEY",
        "default_model": "command-r",
        "models": ["command-r", "command-r-plus"],
    },
    "google_gemini": {
        "env_var": "GOOGLE_GEMINI_API_KEY",
        "default_model": "gemini-2.0-flash",
        "models": [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
            "gemini-1.5-flash-8b",
        ],
    },
}


def _infer_provider(model: str) -> str | None:
    """Infer provider from model name"""
    model_lower = model.lower()
    # OpenRouter models use "org/model" format
    if "/" in model_lower:
        # Check for specific provider prefixes before defaulting to openrouter
        if model_lower.startswith("nvidia/"):
            return "nvidia_nim"
        return "openrouter"
    if "claude" in model_lower:
        return "anthropic"
    if "gpt" in model_lower:
        return "openai"
    if "grok" in model_lower:
        return "xai"
    if "sonar" in model_lower:
        return "perplexity"
    if "helix" in model_lower or "phi" in model_lower or "tinyllama" in model_lower or "qwen" in model_lower:
        return "local"
    if "mixtral" in model_lower and "32768" in model_lower:
        return "groq"
    if "llama" in model_lower and ("versatile" in model_lower or "instant" in model_lower):
        return "groq"
    if "llama" in model_lower:
        return "perplexity"
    if "mistral" in model_lower:
        return "mistral"
    if "gemma" in model_lower:
        return "groq"
    if "minimax" in model_lower:
        return "minimax"
    if "command-r" in model_lower:
        return "cohere"
    if "gemini" in model_lower:
        return "google"
    return None


# ============================================================================
# UNIFIED LLM SERVICE
# ============================================================================


class UnifiedLLMService:
    """
    Single LLM gateway for all Helix systems.

    Auto-discovers available API keys and creates helix_flow provider
    instances. Any system can call generate()/chat() without worrying
    about which SDK to import or how to handle API specifics.
    """

    def __init__(self):
        self._providers: dict[str, Any] = {}
        self._initialized = False
        self._redis = None  # Lazy-loaded for response caching
        self._cache_ttl = int(os.environ.get("LLM_CACHE_TTL", "3600"))  # 1 hour default

    def _ensure_init(self):
        """Lazy initialization — discover available providers on first use"""
        if self._initialized:
            return
        self._initialized = True

        if not HELIX_FLOW_AVAILABLE:
            logger.warning("helix_flow not available, providers will use direct SDK")
            return

        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                self._providers["anthropic"] = AnthropicProvider(
                    config=LLMConfig(model=PROVIDER_REGISTRY["anthropic"]["default_model"])
                )
                logger.info("🌀 Unified LLM: Anthropic provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Anthropic provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Anthropic provider: %s", e)

        # OpenAI
        if os.getenv("OPENAI_API_KEY"):
            try:
                self._providers["openai"] = OpenAIProvider(
                    config=LLMConfig(model=PROVIDER_REGISTRY["openai"]["default_model"])
                )
                logger.info("🌀 Unified LLM: OpenAI provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("OpenAI provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init OpenAI provider: %s", e)

        # xAI / Grok
        if os.getenv("XAI_API_KEY"):
            try:
                self._providers["xai"] = XAIProvider(config=LLMConfig(model=PROVIDER_REGISTRY["xai"]["default_model"]))
                logger.info("🌀 Unified LLM: xAI/Grok provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("xAI provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init xAI provider: %s", e)

        # Perplexity (OpenAI-compatible)
        if os.getenv("PERPLEXITY_API_KEY"):
            try:
                self._providers["perplexity"] = OpenAIProvider(
                    api_key=os.getenv("PERPLEXITY_API_KEY"),
                    base_url="https://api.perplexity.ai",
                    config=LLMConfig(model=PROVIDER_REGISTRY["perplexity"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: Perplexity provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Perplexity provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Perplexity provider: %s", e)

        # OpenRouter (OpenAI-compatible aggregator — 300+ models)
        if os.getenv("OPENROUTER_API_KEY"):
            try:
                self._providers["openrouter"] = OpenAIProvider(
                    api_key=os.getenv("OPENROUTER_API_KEY"),
                    base_url="https://openrouter.ai/api/v1",
                    config=LLMConfig(model=PROVIDER_REGISTRY["openrouter"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: OpenRouter provider ready (300+ models)")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("OpenRouter provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init OpenRouter provider: %s", e)

        # Groq (OpenAI-compatible — ultra-fast inference)
        if os.getenv("GROQ_API_KEY"):
            try:
                self._providers["groq"] = OpenAIProvider(
                    api_key=os.getenv("GROQ_API_KEY"),
                    base_url="https://api.groq.com/openai/v1",
                    config=LLMConfig(model=PROVIDER_REGISTRY["groq"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: Groq provider ready (ultra-fast inference)")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Groq provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Groq provider: %s", e)

        # Mistral (OpenAI-compatible)
        if os.getenv("MISTRAL_API_KEY"):
            try:
                self._providers["mistral"] = OpenAIProvider(
                    api_key=os.getenv("MISTRAL_API_KEY"),
                    base_url="https://api.mistral.ai/v1",
                    config=LLMConfig(model=PROVIDER_REGISTRY["mistral"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: Mistral provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Mistral provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Mistral provider: %s", e)

        # NVIDIA NIM (OpenAI-compatible)
        if os.getenv("NVIDIA_NIM_API_KEY"):
            try:
                self._providers["nvidia_nim"] = OpenAIProvider(
                    api_key=os.getenv("NVIDIA_NIM_API_KEY"),
                    base_url="https://integrate.api.nvidia.com/v1",
                    config=LLMConfig(model=PROVIDER_REGISTRY["nvidia_nim"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: NVIDIA NIM provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("NVIDIA NIM provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init NVIDIA NIM provider: %s", e)

        # MiniMax (OpenAI-compatible)
        if os.getenv("MINIMAX_API_KEY"):
            try:
                self._providers["minimax"] = OpenAIProvider(
                    api_key=os.getenv("MINIMAX_API_KEY"),
                    base_url="https://api.minimax.chat/v1",
                    config=LLMConfig(model=PROVIDER_REGISTRY["minimax"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: MiniMax provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("MiniMax provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init MiniMax provider: %s", e)

        # Google Gemini via OpenAI-compatible endpoint
        if os.getenv("GOOGLE_GEMINI_API_KEY"):
            try:
                self._providers["google_gemini"] = OpenAIProvider(
                    api_key=os.getenv("GOOGLE_GEMINI_API_KEY"),
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai",
                    config=LLMConfig(model=PROVIDER_REGISTRY["google_gemini"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: Google Gemini (free tier) provider ready")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Google Gemini provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Google Gemini provider: %s", e)

        # Cohere (NOT OpenAI-compatible — uses Cohere SDK)
        if os.getenv("COHERE_API_KEY"):
            try:
                from apps.backend.helix_flow.llm import CohereProvider as FlowCohereProvider

                self._providers["cohere"] = FlowCohereProvider(
                    config=LLMConfig(model=PROVIDER_REGISTRY["cohere"]["default_model"]),
                )
                logger.info("🌀 Unified LLM: Cohere provider ready")
            except ImportError:
                logger.debug("Cohere SDK not installed, skipping provider")
            except (ValueError, TypeError, KeyError) as e:
                logger.debug("Cohere provider configuration error: %s", e)
            except Exception as e:
                logger.warning("Failed to init Cohere provider: %s", e)

        # Local LLM (Helix AI - CPU inference via llama.cpp)
        # Enabled when HELIX_LOCAL_MODEL is set or a model file exists
        if os.getenv("HELIX_LOCAL_MODEL") or os.getenv("HELIX_LOCAL_MODEL_PATH"):
            try:
                from apps.backend.services.local_llm_provider import get_local_provider

                local_provider = get_local_provider()
                self._providers["local"] = local_provider
                logger.info("🌀 Unified LLM: Local/Helix AI provider registered (lazy init)")
            except Exception as e:
                logger.warning("Failed to init local LLM provider: %s", e)

        # Helix Native LLM Engine (dedicated Railway service via HTTP)
        # Registered when LLM_ENGINE_URL is set; placed last so it only runs
        # when all cloud providers are unavailable or explicitly requested.
        llm_engine_url = os.getenv("LLM_ENGINE_URL")
        if llm_engine_url:
            try:
                self._providers["helix_native"] = _HelixEngineProvider(llm_engine_url)
                logger.info("🧠 Unified LLM: Helix Native Engine registered at %s", llm_engine_url)
            except Exception as e:
                logger.warning("Failed to register Helix Engine provider: %s", e)

        if not self._providers:
            logger.warning(
                "🌀 Unified LLM: No API keys found. Set ANTHROPIC_API_KEY, "
                "OPENAI_API_KEY, or XAI_API_KEY to enable LLM features."
            )

    # ------------------------------------------------------------------
    # Provider selection
    # ------------------------------------------------------------------

    @property
    def providers(self) -> dict[str, Any]:
        """Get dict of configured providers (HelixConsciousAgent compatibility)."""
        self._ensure_init()
        return self._providers

    def get_available_providers(self) -> list[str]:
        """Get list of configured provider names"""
        self._ensure_init()
        return list(self._providers.keys())

    async def _resolve_provider(
        self,
        provider: str | None = None,
        model: str | None = None,
        user_id: str | None = None,
    ) -> tuple:
        """
        Resolve provider + model, respecting BYOT keys when user_id is given.

        If user has a BYOT key for the target provider, creates a one-off
        provider instance using their personal key. Otherwise falls back to
        platform providers.
        """
        self._ensure_init()

        # Determine target provider name
        target_provider = provider
        if not target_provider and model:
            target_provider = _infer_provider(model)
        if not target_provider:
            # Auto-select: cloud first; helix_native (Qwen 2.5 on llm-engine) before local
            preference = ["anthropic", "xai", "openai", "perplexity", "openrouter", "helix_native", "local"]
            for pref in preference:
                if pref in self._providers:
                    target_provider = pref
                    break
            if not target_provider and self._providers:
                target_provider = next(iter(self._providers))

        if not target_provider:
            return None, model or "none"

        resolved_model = model or PROVIDER_REGISTRY.get(target_provider, {}).get("default_model", "unknown")

        # Try BYOT key if user_id provided
        if user_id and HELIX_FLOW_AVAILABLE:
            try:
                from apps.backend.services.byot_service import get_effective_llm_key

                byot_key = await get_effective_llm_key(user_id, target_provider)
                # Check if BYOT key differs from platform key (i.e. user has own key)
                platform_key = os.getenv(PROVIDER_REGISTRY.get(target_provider, {}).get("env_var", ""), "")
                if byot_key and byot_key != platform_key:
                    # Create a one-off provider with the user's key
                    prov = self._create_provider(target_provider, api_key=byot_key)
                    if prov:
                        logger.debug("Using BYOT key for user %s on %s", user_id, target_provider)
                        return prov, resolved_model
            except Exception as e:
                logger.debug("BYOT lookup failed, using platform key: %s", e)

        # Use cached platform provider
        if target_provider in self._providers:
            return self._providers[target_provider], resolved_model

        # No provider available
        return None, resolved_model

    def _create_provider(self, provider_name: str, api_key: str) -> Any | None:
        """Create a one-off provider instance with a specific API key."""
        if not HELIX_FLOW_AVAILABLE:
            return None
        try:
            default_model = PROVIDER_REGISTRY.get(provider_name, {}).get("default_model", "")
            config = LLMConfig(model=default_model)
            if provider_name == "anthropic":
                return AnthropicProvider(api_key=api_key, config=config)
            elif provider_name in ("openai", "perplexity"):
                kwargs = {"api_key": api_key, "config": config}
                if provider_name == "perplexity":
                    kwargs["base_url"] = "https://api.perplexity.ai"
                return OpenAIProvider(**kwargs)
            elif provider_name == "openrouter":
                return OpenAIProvider(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    config=config,
                )
            elif provider_name == "xai":
                return XAIProvider(api_key=api_key, config=config)
        except Exception as e:
            logger.warning("Failed to create BYOT provider %s: %s", provider_name, e)
        return None

    def _select_provider(
        self,
        provider: str | None = None,
        model: str | None = None,
    ) -> tuple:
        """
        Select best provider + model based on request (sync, no BYOT).
        For BYOT-aware selection, use _resolve_provider() instead.

        Priority:
        1. Explicit provider requested
        2. Provider inferred from model name
        3. First available in preference order: anthropic > xai > openai > perplexity
        """
        self._ensure_init()

        if not self._providers:
            return None, model or "none"

        # Explicit provider
        if provider and provider in self._providers:
            resolved_model = model or PROVIDER_REGISTRY[provider]["default_model"]
            return self._providers[provider], resolved_model

        # Infer from model name
        if model:
            inferred = _infer_provider(model)
            if inferred and inferred in self._providers:
                return self._providers[inferred], model

        # Auto-select: prefer anthropic > xai > openai > openrouter > perplexity
        preference = ["anthropic", "xai", "openai", "openrouter", "perplexity"]
        for pref in preference:
            if pref in self._providers:
                resolved_model = model or PROVIDER_REGISTRY[pref]["default_model"]
                return self._providers[pref], resolved_model

        # Fallback to first available
        first_name = next(iter(self._providers))
        return self._providers[first_name], model or PROVIDER_REGISTRY.get(first_name, {}).get(
            "default_model", "unknown"
        )

    def _provider_name(self, provider_obj) -> str:
        """Get provider name string from provider object"""
        if hasattr(provider_obj, "name"):
            return provider_obj.name
        return "unknown"

    # ------------------------------------------------------------------
    # Core API
    # ------------------------------------------------------------------

    @retry_with_backoff(max_retries=2, base_delay=0.5, exceptions=(Exception,))
    async def _call_provider(
        self,
        provider_obj: Any,
        messages: list[dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Any:
        """Call LLM provider with retry. Isolated so retries target the HTTP call only."""
        return await provider_obj.chat(
            messages=messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    async def generate(
        self,
        prompt: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
        user_id: str | None = None,
    ) -> str:
        """
        Generate text from a prompt. Returns string content.

        Args:
            prompt: The user prompt
            model: Specific model name (e.g. "grok-3-mini", "claude-3-haiku-20240307")
            provider: Force a specific provider ("anthropic", "openai", "xai", "perplexity")
            max_tokens: Max tokens in response
            temperature: Sampling temperature
            system: Optional system prompt
            user_id: Optional user ID for BYOT key lookup

        Returns:
            Generated text string. Empty string on failure.
        """
        resp = await self.generate_with_metadata(
            prompt,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            user_id=user_id,
        )
        return resp.content

    async def generate_with_metadata(
        self,
        prompt: str,
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        system: str | None = None,
        user_id: str | None = None,
    ) -> UnifiedLLMResponse:
        """Generate text and return full response with metadata."""
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        return await self.chat_with_metadata(
            messages,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            user_id=user_id,
        )

    async def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> str:
        """
        Chat completion. Returns string content.

        Args:
            messages: List of {"role": "...", "content": "..."} dicts
            model: Specific model name
            provider: Force a specific provider
            max_tokens: Max tokens
            temperature: Sampling temperature
            user_id: Optional user ID for BYOT key lookup

        Returns:
            Assistant response text. Empty string on failure.
        """
        resp = await self.chat_with_metadata(
            messages,
            model=model,
            provider=provider,
            max_tokens=max_tokens,
            temperature=temperature,
            user_id=user_id,
        )
        return resp.content

    # ------------------------------------------------------------------
    # Response Cache (Redis-backed)
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Lazily connect to Redis for caching."""
        if self._redis is not None:
            return self._redis
        try:
            from apps.backend.core.redis_client import get_redis_client

            self._redis = await get_redis_client()
        except Exception as e:
            self._redis = False  # Sentinel: don't retry
            logging.getLogger(__name__).debug("Redis connection failed, caching disabled: %s", e)
        return self._redis if self._redis else None

    @staticmethod
    def _cache_key(messages: list[dict[str, str]], model: str, temperature: float, max_tokens: int) -> str:
        """Build a deterministic cache key from request params."""
        payload = _json.dumps(
            {
                "m": messages,
                "model": model,
                "t": temperature,
                "mt": max_tokens,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        digest = hashlib.sha256(payload.encode()).hexdigest()[:32]
        return f"llm_cache:{digest}"

    async def _cache_get(self, key: str) -> UnifiedLLMResponse | None:
        """Try to load a cached LLM response."""
        redis = await self._get_redis()
        if not redis:
            return None
        try:
            raw = await redis.get(key)
            if raw is None:
                return None
            data = _json.loads(raw)
            resp = UnifiedLLMResponse(
                content=data["content"],
                model=data["model"],
                provider=data["provider"] + "/cache",
                usage=data.get("usage", {}),
                finish_reason=data.get("finish_reason", "stop"),
            )
            logger.debug("LLM cache HIT: %s (model=%s)", key, resp.model)
            return resp
        except Exception as e:
            logger.debug("LLM cache get failed: %s", e)
            return None

    async def _cache_set(self, key: str, resp: UnifiedLLMResponse) -> None:
        """Store an LLM response in cache."""
        redis = await self._get_redis()
        if not redis:
            return
        try:
            data = _json.dumps(
                {
                    "content": resp.content,
                    "model": resp.model,
                    "provider": resp.provider,
                    "usage": resp.usage,
                    "finish_reason": resp.finish_reason,
                }
            )
            await redis.setex(key, self._cache_ttl, data)
            logger.debug("LLM cache SET: %s (ttl=%ds)", key, self._cache_ttl)
        except Exception as e:
            logger.debug("LLM cache set failed: %s", e)

    async def chat_with_metadata(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> UnifiedLLMResponse:
        """
        Chat completion with full metadata.

        Args:
            messages: Chat messages
            model: Specific model name
            provider: Force a specific provider
            max_tokens: Max tokens
            temperature: Sampling temperature
            user_id: Optional user ID — when provided, uses BYOT key if available

        Returns UnifiedLLMResponse with content, model, provider, usage, etc.
        On failure, returns response with error field set and empty content.
        """
        # ── Response cache check ──────────────────────────────────────
        # Only cache when temperature ≤ 0.2 (deterministic queries).
        # High temperature implies the caller wants variety.
        use_cache = temperature <= 0.2 and self._cache_ttl > 0
        cache_key = None
        if use_cache:
            cache_key = self._cache_key(messages, model or "auto", temperature, max_tokens)
            cached = await self._cache_get(cache_key)
            if cached is not None:
                return cached

        provider_obj, resolved_model = await self._resolve_provider(provider, model, user_id)

        if provider_obj is None:
            logger.warning("No LLM providers configured")
            return UnifiedLLMResponse(
                content="",
                model=resolved_model,
                provider="none",
                error="No LLM API keys configured. Set ANTHROPIC_API_KEY, OPENAI_API_KEY, or XAI_API_KEY.",
            )

        provider_name = self._provider_name(provider_obj)

        try:
            flow_response: FlowLLMResponse = await self._call_provider(
                provider_obj, messages, resolved_model, max_tokens, temperature
            )

            response = UnifiedLLMResponse(
                content=flow_response.content,
                model=flow_response.model or resolved_model,
                provider=provider_name,
                usage=flow_response.usage,
                finish_reason=flow_response.finish_reason,
            )

            # Store in cache if applicable
            if use_cache and cache_key and response.content:
                await self._cache_set(cache_key, response)

            # Fire-and-forget cost tracking — never blocks the caller
            if user_id and response.usage:
                try:
                    from apps.backend.config.credit_pricing import calculate_request_cost
                    from apps.backend.core.unified_auth import track_usage

                    tokens_in = response.usage.get("prompt_tokens", 0) or response.usage.get("input_tokens", 0)
                    tokens_out = response.usage.get("completion_tokens", 0) or response.usage.get("output_tokens", 0)
                    cost = calculate_request_cost(response.model, tokens_in, tokens_out)
                    await track_usage(
                        user_id=user_id,
                        endpoint="/internal/llm/chat",
                        method="POST",
                        provider=provider_name,
                        model=response.model,
                        tokens_input=tokens_in,
                        tokens_output=tokens_out,
                        cost_usd=cost,
                    )
                except Exception as _te:
                    logger.debug("LLM cost tracking skipped: %s", _te)

            return response

        except Exception as e:
            logger.error("Unified LLM call failed (%s/%s): %s", provider_name, resolved_model, e)

            # Try fallback providers
            fallback_result = await self._try_fallbacks(
                messages, resolved_model, provider_name, max_tokens, temperature
            )
            if fallback_result:
                return fallback_result

            return UnifiedLLMResponse(
                content="",
                model=resolved_model,
                provider=provider_name,
                error=str(e),
            )

    async def chat_with_tools(
        self,
        messages: list[dict[str, str]],
        *,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 2048,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> UnifiedLLMResponse:
        """
        Chat completion with tool/function calling support.

        When tools are provided, the response may contain tool_calls
        instead of (or in addition to) text content. Tool definitions
        should use the standard JSON Schema format:
        [{"name": "tool_name", "description": "...", "parameters": {...}}]

        Returns UnifiedLLMResponse with populated .tool_calls field
        when the LLM wants to call tools.
        """
        provider_obj, resolved_model = await self._resolve_provider(provider, model, user_id)

        if provider_obj is None:
            logger.warning("No LLM providers configured")
            return UnifiedLLMResponse(
                content="",
                model=resolved_model or "none",
                provider="none",
                error="No LLM API keys configured.",
            )

        provider_name = self._provider_name(provider_obj)

        try:
            flow_response = await provider_obj.chat(
                messages=messages,
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=temperature,
                tools=tools,
            )

            # Normalize tool_calls from provider response
            raw_tool_calls = getattr(flow_response, "tool_calls", None) or []
            normalized_calls = []
            for tc in raw_tool_calls:
                if hasattr(tc, "function"):
                    # OpenAI format: ChatCompletionMessageToolCall
                    import json as _json

                    args = tc.function.arguments
                    if isinstance(args, str):
                        try:
                            args = _json.loads(args)
                        except _json.JSONDecodeError:
                            args = {"raw": args}
                    normalized_calls.append(
                        {
                            "id": tc.id,
                            "name": tc.function.name,
                            "arguments": args,
                        }
                    )
                elif isinstance(tc, dict):
                    # Already a dict (e.g., Anthropic format)
                    normalized_calls.append(
                        {
                            "id": tc.get("id", ""),
                            "name": tc.get("name", ""),
                            "arguments": tc.get("input", tc.get("arguments", {})),
                        }
                    )

            return UnifiedLLMResponse(
                content=flow_response.content or "",
                model=flow_response.model or resolved_model,
                provider=provider_name,
                usage=flow_response.usage,
                finish_reason=flow_response.finish_reason,
                tool_calls=normalized_calls if normalized_calls else None,
            )

        except Exception as e:
            logger.error("Unified LLM tool call failed (%s/%s): %s", provider_name, resolved_model, e)
            return UnifiedLLMResponse(
                content="",
                model=resolved_model or "unknown",
                provider=provider_name,
                error=str(e),
            )

    async def _try_fallbacks(
        self,
        messages: list[dict[str, str]],
        original_model: str,
        failed_provider: str,
        max_tokens: int,
        temperature: float,
    ) -> UnifiedLLMResponse | None:
        """Try other available providers as fallback"""
        for name, prov in self._providers.items():
            if name == failed_provider:
                continue
            try:
                fallback_model = PROVIDER_REGISTRY[name]["default_model"]
                flow_response = await prov.chat(
                    messages=messages,
                    model=fallback_model,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )
                logger.info("Fallback to %s succeeded", name)
                return UnifiedLLMResponse(
                    content=flow_response.content,
                    model=flow_response.model or fallback_model,
                    provider=name,
                    usage=flow_response.usage,
                    finish_reason=flow_response.finish_reason,
                )
            except Exception as e:
                logger.debug("Fallback %s also failed: %s", name, e)
                continue
        return None

    async def structured_chat(
        self,
        messages: list[dict[str, str]],
        response_model: type,
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
        max_retries: int = 3,
        user_id: str | None = None,
    ) -> Any:
        """
        Instructor-style structured output: call the LLM and validate the
        response against a Pydantic model, retrying with the validation error
        as feedback on each failed attempt (up to *max_retries*).

        Args:
            messages: Chat messages (same format as chat()).
            response_model: A Pydantic BaseModel subclass describing the
                            expected output shape.
            model: Specific model name override.
            provider: Force a specific provider.
            max_tokens: Max tokens for the completion.
            temperature: Sampling temperature (default 0.2 for structured output).
            max_retries: Maximum validation-retry attempts before raising.
            user_id: Optional user ID for BYOT key lookup.

        Returns:
            An instance of *response_model* on success.

        Raises:
            ValueError: If the model repeatedly returns unparseable/invalid JSON.
        """
        import json as _j

        try:
            from pydantic import ValidationError as _ValidationError  # noqa: F401 — availability check only
        except ImportError as e:
            raise RuntimeError("pydantic is required for structured_chat()") from e

        # Inject a schema-aware system instruction
        schema = response_model.model_json_schema() if hasattr(response_model, "model_json_schema") else {}
        schema_str = _j.dumps(schema, indent=2)
        instruction = (
            "Respond ONLY with a valid JSON object that conforms to this schema. "
            "Do not include markdown, code fences, or any prose outside the JSON.\n\n"
            f"Schema:\n{schema_str}"
        )

        working_messages = list(messages)
        # Prepend or extend an existing system message
        if working_messages and working_messages[0].get("role") == "system":
            working_messages[0] = {
                "role": "system",
                "content": working_messages[0]["content"] + "\n\n" + instruction,
            }
        else:
            working_messages.insert(0, {"role": "system", "content": instruction})

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            response = await self.chat(
                working_messages,
                model=model,
                provider=provider,
                max_tokens=max_tokens,
                temperature=temperature,
                user_id=user_id,
            )

            raw = response.content.strip() if response.content else ""

            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("```", 2)[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.rstrip("` \n")

            try:
                parsed = _j.loads(raw)
                return response_model(**parsed)
            except (_j.JSONDecodeError, Exception) as e:
                last_error = e
                logger.warning(
                    "structured_chat attempt %d/%d failed (%s): %s",
                    attempt,
                    max_retries,
                    type(e).__name__,
                    str(e)[:200],
                )
                if attempt < max_retries:
                    # Feed the error back to the model as a correction request
                    working_messages.append({"role": "assistant", "content": raw})
                    working_messages.append(
                        {
                            "role": "user",
                            "content": (
                                f"That response was invalid. Error: {e}\n"
                                "Please reply with only a valid JSON object matching the schema."
                            ),
                        }
                    )

        raise ValueError(
            f"structured_chat: failed to get valid {response_model.__name__} "
            f"after {max_retries} attempts. Last error: {last_error}"
        )

    async def stream(
        self,
        prompt: str,
        *,
        model: str | None = None,
        provider: str | None = None,
    ) -> AsyncIterator[str]:
        """Stream tokens from the selected provider."""
        provider_obj, _resolved_model = self._select_provider(provider, model)
        if provider_obj is None:
            yield ""
            return

        async for token in provider_obj.stream(prompt):
            yield token

    async def chat_stream(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        provider: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.7,
        user_id: str | None = None,
    ) -> AsyncIterator[str]:
        """
        Stream chat completion tokens.

        Uses the provider's chat_stream() for true token-by-token streaming.
        Falls back to non-streaming chat() if chat_stream is not overridden.

        Args:
            messages: Chat messages
            model: Specific model name
            provider: Force a specific provider
            max_tokens: Max tokens
            temperature: Sampling temperature
            user_id: Optional user ID for BYOT key lookup
        """
        provider_obj, resolved_model = await self._resolve_provider(provider, model, user_id)

        if provider_obj is None:
            yield ""
            return

        try:
            async for token in provider_obj.chat_stream(
                messages,
                model=resolved_model,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                yield token
        except Exception as e:
            logger.error("Streaming failed (%s): %s", self._provider_name(provider_obj), e)
            # Fallback: do a non-streaming call and yield the whole response
            try:
                resp = await self.chat_with_metadata(
                    messages,
                    model=model,
                    provider=provider,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    user_id=user_id,
                )
                if resp.content:
                    yield resp.content
            except Exception as e:
                logging.getLogger(__name__).warning("LLM streaming chunk failed: %s", e)
                yield ""

    # ------------------------------------------------------------------
    # Google Gemini (special handling — not OpenAI-compatible)
    # ------------------------------------------------------------------

    async def chat_gemini(
        self,
        prompt: str,
        *,
        model: str = "gemini-2.0-flash",
        max_tokens: int = 1024,
    ) -> UnifiedLLMResponse:
        """
        Call Google Gemini API (not OpenAI-compatible, needs special handling).
        Uses google-generativeai SDK.
        """
        import asyncio as _asyncio

        try:
            import google.generativeai as genai

            api_key = os.getenv("GOOGLE_AI_KEY")
            if not api_key:
                return UnifiedLLMResponse(
                    content="",
                    model=model,
                    provider="google",
                    error="GOOGLE_AI_KEY not set",
                )
            genai.configure(api_key=api_key)
            gmodel = genai.GenerativeModel(model)
            response = await _asyncio.to_thread(
                gmodel.generate_content,
                prompt,
                generation_config=genai.types.GenerationConfig(max_output_tokens=max_tokens),
            )
            return UnifiedLLMResponse(
                content=response.text if response else "",
                model=model,
                provider="google",
                usage={"total_tokens": 0},
            )
        except ImportError:
            return UnifiedLLMResponse(
                content="",
                model=model,
                provider="google",
                error="google-generativeai package not installed",
            )
        except Exception as e:
            logger.error("Gemini call failed: %s", e)
            return UnifiedLLMResponse(
                content="",
                model=model,
                provider="google",
                error=str(e),
            )


# ============================================================================
# GLOBAL SINGLETON
# ============================================================================

unified_llm = UnifiedLLMService()


def get_unified_llm() -> UnifiedLLMService:
    """Return the global UnifiedLLMService singleton.

    Compatibility function for HelixConsciousAgent and other callers
    that expect a ``get_unified_llm()`` factory.
    """
    return unified_llm


__all__ = [
    "PROVIDER_REGISTRY",
    "UnifiedLLMResponse",
    "UnifiedLLMService",
    "get_unified_llm",
    "unified_llm",
    # structured_chat is a method on UnifiedLLMService — listed here for discoverability
    # Usage: result = await unified_llm.structured_chat(messages, MyPydanticModel)
]
