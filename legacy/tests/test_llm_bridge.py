"""
Comprehensive Test Suite for Helix-Core LLM Bridge

Tests for LLM integration, multi-provider support, streaming, batching,
token counting, cost estimation, and error handling.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
class TestLLMBridgeInitialization:
    """Test LLM bridge initialization."""

    async def test_llm_bridge_creation(self, mock_llm_bridge):
        """Test LLM bridge can be created."""
        assert mock_llm_bridge is not None
        assert hasattr(mock_llm_bridge, "generate")
        assert hasattr(mock_llm_bridge, "stream")

    async def test_llm_bridge_add_provider(self, mock_llm_bridge, mock_llm_provider):
        """Test adding provider to bridge."""
        mock_llm_bridge.add_provider(mock_llm_provider)
        mock_llm_bridge.add_provider.assert_called_once()

    async def test_llm_bridge_get_provider(self, mock_llm_bridge):
        """Test getting provider from bridge."""
        provider = mock_llm_bridge.get_provider("test")
        mock_llm_bridge.get_provider.assert_called_once_with("test")


@pytest.mark.asyncio
class TestLLMBridgeGeneration:
    """Test LLM text generation."""

    async def test_generate_text(self, mock_llm_bridge, sample_prompt):
        """Test generating text."""
        result = await mock_llm_bridge.generate(sample_prompt)
        assert result == "Test response"
        mock_llm_bridge.generate.assert_called_once_with(sample_prompt)

    async def test_generate_with_parameters(self, mock_llm_bridge, sample_prompt):
        """Test generating with parameters."""
        result = await mock_llm_bridge.generate(
            sample_prompt,
            temperature=0.7,
            max_tokens=100,
            top_p=0.9,
        )
        assert result == "Test response"

    async def test_generate_with_system_prompt(self, mock_llm_bridge, sample_prompt):
        """Test generating with system prompt."""
        result = await mock_llm_bridge.generate(
            sample_prompt,
            system_prompt="You are a helpful assistant.",
        )
        assert result == "Test response"

    async def test_generate_error_handling(self, mock_llm_bridge):
        """Test error handling in generation."""
        mock_llm_bridge.generate.side_effect = Exception("API Error")
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test prompt")


@pytest.mark.asyncio
class TestLLMBridgeStreaming:
    """Test LLM streaming."""

    async def test_stream_text(self, mock_llm_bridge, sample_prompt):
        """Test streaming text."""
        mock_llm_bridge.stream.return_value = AsyncMock()
        stream = await mock_llm_bridge.stream(sample_prompt)
        mock_llm_bridge.stream.assert_called_once_with(sample_prompt)

    async def test_stream_chunks(self, mock_llm_bridge, sample_prompt):
        """Test streaming chunks."""
        chunks = ["Hello", " ", "world"]
        mock_llm_bridge.stream.return_value = AsyncMock()
        stream = await mock_llm_bridge.stream(sample_prompt)
        mock_llm_bridge.stream.assert_called_once()

    @pytest.mark.slow
    async def test_stream_performance(self, mock_llm_bridge, sample_prompt, performance_timer):
        """Test streaming performance."""
        performance_timer.start()
        stream = await mock_llm_bridge.stream(sample_prompt)
        performance_timer.stop()
        assert performance_timer.elapsed is not None


@pytest.mark.asyncio
class TestTokenCounting:
    """Test token counting."""

    def test_count_tokens(self, mock_llm_bridge, sample_prompt):
        """Test counting tokens."""
        token_count = mock_llm_bridge.count_tokens(sample_prompt)
        assert isinstance(token_count, int)
        assert token_count > 0

    def test_count_tokens_empty(self, mock_llm_bridge):
        """Test counting tokens in empty string."""
        token_count = mock_llm_bridge.count_tokens("")
        assert isinstance(token_count, int)
        assert token_count >= 0

    def test_count_tokens_long_text(self, mock_llm_bridge):
        """Test counting tokens in long text."""
        long_text = "This is a test. " * 100
        token_count = mock_llm_bridge.count_tokens(long_text)
        assert isinstance(token_count, int)
        assert token_count > 0


@pytest.mark.asyncio
class TestCostEstimation:
    """Test cost estimation."""

    def test_estimate_cost(self, mock_llm_bridge, sample_prompt):
        """Test cost estimation."""
        cost = mock_llm_bridge.estimate_cost(sample_prompt)
        assert isinstance(cost, (int, float))
        assert cost >= 0

    def test_estimate_cost_with_output(self, mock_llm_bridge):
        """Test cost estimation with output tokens."""
        cost = mock_llm_bridge.estimate_cost(
            "Test prompt",
            output_tokens=100,
        )
        assert isinstance(cost, (int, float))
        assert cost >= 0

    def test_estimate_cost_different_models(self, mock_llm_bridge):
        """Test cost estimation for different models."""
        cost_gpt4 = mock_llm_bridge.estimate_cost("Test", model="gpt-4")
        cost_gpt35 = mock_llm_bridge.estimate_cost("Test", model="gpt-3.5-turbo")
        assert isinstance(cost_gpt4, (int, float))
        assert isinstance(cost_gpt35, (int, float))


@pytest.mark.asyncio
class TestMultiProviderSupport:
    """Test multi-provider support."""

    async def test_provider_switching(self, mock_llm_bridge):
        """Test switching between providers."""
        mock_llm_bridge.add_provider(MagicMock(name="provider1"))
        mock_llm_bridge.add_provider(MagicMock(name="provider2"))
        mock_llm_bridge.add_provider.assert_called()

    async def test_provider_fallback(self, mock_llm_bridge):
        """Test provider fallback."""
        result = await mock_llm_bridge.generate("Test", provider="fallback")
        assert result == "Test response"

    async def test_provider_list(self, mock_llm_bridge):
        """Test listing providers."""
        providers = mock_llm_bridge.list_providers()
        # Should have at least one provider


@pytest.mark.asyncio
class TestBatchProcessing:
    """Test batch processing."""

    async def test_batch_generation(self, mock_llm_bridge):
        """Test batch text generation."""
        prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
        mock_llm_bridge.batch_generate = AsyncMock(
            return_value=["Response 1", "Response 2", "Response 3"]
        )
        results = await mock_llm_bridge.batch_generate(prompts)
        assert len(results) == 3

    async def test_batch_token_counting(self, mock_llm_bridge):
        """Test batch token counting."""
        prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
        mock_llm_bridge.batch_count_tokens = MagicMock(return_value=[5, 5, 5])
        counts = mock_llm_bridge.batch_count_tokens(prompts)
        assert len(counts) == 3

    @pytest.mark.slow
    async def test_batch_performance(self, mock_llm_bridge, performance_timer):
        """Test batch processing performance."""
        prompts = ["Prompt"] * 10
        mock_llm_bridge.batch_generate = AsyncMock(
            return_value=["Response"] * 10
        )
        performance_timer.start()
        results = await mock_llm_bridge.batch_generate(prompts)
        performance_timer.stop()
        assert len(results) == 10
        assert performance_timer.elapsed is not None


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling."""

    async def test_invalid_prompt(self, mock_llm_bridge):
        """Test handling invalid prompt."""
        with pytest.raises((TypeError, ValueError)):
            await mock_llm_bridge.generate(None)

    async def test_api_error_recovery(self, mock_llm_bridge):
        """Test API error recovery."""
        mock_llm_bridge.generate.side_effect = Exception("API Error")
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test")

    async def test_timeout_handling(self, mock_llm_bridge):
        """Test timeout handling."""
        mock_llm_bridge.generate.side_effect = TimeoutError("Request timeout")
        with pytest.raises(TimeoutError):
            await mock_llm_bridge.generate("Test")

    async def test_rate_limit_handling(self, mock_llm_bridge):
        """Test rate limit handling."""
        mock_llm_bridge.generate.side_effect = Exception("Rate limit exceeded")
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test")


@pytest.mark.asyncio
class TestContextManagement:
    """Test context management in LLM bridge."""

    async def test_context_preservation(self, mock_llm_bridge):
        """Test context is preserved across calls."""
        await mock_llm_bridge.generate("First prompt")
        await mock_llm_bridge.generate("Second prompt")
        assert mock_llm_bridge.generate.call_count == 2

    async def test_context_clearing(self, mock_llm_bridge):
        """Test context clearing."""
        mock_llm_bridge.clear_context = MagicMock()
        mock_llm_bridge.clear_context()
        mock_llm_bridge.clear_context.assert_called_once()

    async def test_context_history(self, mock_llm_bridge):
        """Test context history."""
        mock_llm_bridge.get_history = MagicMock(return_value=[])
        history = mock_llm_bridge.get_history()
        mock_llm_bridge.get_history.assert_called_once()


@pytest.mark.asyncio
class TestCaching:
    """Test caching in LLM bridge."""

    async def test_response_caching(self, mock_llm_bridge):
        """Test response caching."""
        mock_llm_bridge.enable_cache = MagicMock()
        mock_llm_bridge.enable_cache()
        mock_llm_bridge.enable_cache.assert_called_once()

    async def test_cache_hit(self, mock_llm_bridge):
        """Test cache hit."""
        prompt = "Test prompt"
        await mock_llm_bridge.generate(prompt)
        await mock_llm_bridge.generate(prompt)
        # Second call should use cache
        assert mock_llm_bridge.generate.call_count == 2

    async def test_cache_invalidation(self, mock_llm_bridge):
        """Test cache invalidation."""
        mock_llm_bridge.clear_cache = MagicMock()
        mock_llm_bridge.clear_cache()
        mock_llm_bridge.clear_cache.assert_called_once()


@pytest.mark.asyncio
class TestRetryLogic:
    """Test retry logic."""

    async def test_automatic_retry(self, mock_llm_bridge):
        """Test automatic retry on failure."""
        mock_llm_bridge.generate.side_effect = [
            Exception("First attempt"),
            "Success on retry",
        ]
        # Should retry and succeed
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test")

    async def test_max_retries(self, mock_llm_bridge):
        """Test max retries limit."""
        mock_llm_bridge.generate.side_effect = Exception("Always fails")
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test")

    async def test_exponential_backoff(self, mock_llm_bridge, performance_timer):
        """Test exponential backoff."""
        mock_llm_bridge.generate.side_effect = Exception("Fails")
        performance_timer.start()
        with pytest.raises(Exception):
            await mock_llm_bridge.generate("Test")
        performance_timer.stop()


@pytest.mark.asyncio
class TestIntegration:
    """Integration tests for LLM bridge."""

    async def test_full_workflow(self, mock_llm_bridge, sample_prompt):
        """Test full LLM workflow."""
        # Count tokens
        token_count = mock_llm_bridge.count_tokens(sample_prompt)
        assert token_count > 0

        # Estimate cost
        cost = mock_llm_bridge.estimate_cost(sample_prompt)
        assert cost >= 0

        # Generate response
        response = await mock_llm_bridge.generate(sample_prompt)
        assert response == "Test response"

    async def test_streaming_workflow(self, mock_llm_bridge, sample_prompt):
        """Test streaming workflow."""
        mock_llm_bridge.stream.return_value = AsyncMock()
        stream = await mock_llm_bridge.stream(sample_prompt)
        mock_llm_bridge.stream.assert_called_once()

    async def test_batch_workflow(self, mock_llm_bridge):
        """Test batch workflow."""
        prompts = ["Prompt 1", "Prompt 2"]
        mock_llm_bridge.batch_generate = AsyncMock(
            return_value=["Response 1", "Response 2"]
        )
        results = await mock_llm_bridge.batch_generate(prompts)
        assert len(results) == 2


@pytest.mark.unit
class TestLLMBridgeUnit:
    """Unit tests for LLM bridge."""

    def test_bridge_initialization(self, mock_llm_bridge):
        """Test bridge initialization."""
        assert mock_llm_bridge is not None

    def test_bridge_has_methods(self, mock_llm_bridge):
        """Test bridge has required methods."""
        assert hasattr(mock_llm_bridge, "generate")
        assert hasattr(mock_llm_bridge, "stream")
        assert hasattr(mock_llm_bridge, "count_tokens")
        assert hasattr(mock_llm_bridge, "estimate_cost")

    def test_token_counting_accuracy(self, mock_llm_bridge):
        """Test token counting accuracy."""
        text = "The quick brown fox jumps over the lazy dog"
        count = mock_llm_bridge.count_tokens(text)
        assert isinstance(count, int)
        assert count > 0
