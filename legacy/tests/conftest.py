"""
Pytest Configuration and Fixtures for Helix-Core

Provides comprehensive fixtures, mocks, and utilities for testing helix-core components.
"""

import asyncio
import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


# =============================================================================
# PYTEST HOOKS
# =============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "asyncio: Async tests")


# =============================================================================
# EVENT LOOP FIXTURES
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def async_context():
    """Provide async context for tests."""
    yield
    await asyncio.sleep(0)


# =============================================================================
# MOCK LLM FIXTURES
# =============================================================================

@pytest.fixture
def mock_llm_response():
    """Mock LLM response."""
    return {
        "id": "test-response-1",
        "object": "text_completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [
            {
                "text": "This is a test response from the LLM.",
                "finish_reason": "stop",
                "index": 0,
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 15,
            "total_tokens": 25,
        },
    }


@pytest.fixture
def mock_llm_provider():
    """Mock LLM provider."""
    provider = AsyncMock()
    provider.name = "test-provider"
    provider.model = "test-model"
    provider.generate = AsyncMock(
        return_value="Test response from LLM"
    )
    provider.stream = AsyncMock()
    provider.count_tokens = MagicMock(return_value=25)
    provider.estimate_cost = MagicMock(return_value=0.001)
    return provider


@pytest.fixture
def mock_llm_bridge():
    """Mock LLM bridge."""
    bridge = AsyncMock()
    bridge.generate = AsyncMock(return_value="Test response")
    bridge.stream = AsyncMock()
    bridge.count_tokens = MagicMock(return_value=25)
    bridge.estimate_cost = MagicMock(return_value=0.001)
    bridge.add_provider = MagicMock()
    bridge.get_provider = MagicMock()
    return bridge


# =============================================================================
# MOCK TOOL FIXTURES
# =============================================================================

@pytest.fixture
def mock_tool():
    """Mock tool."""
    tool = MagicMock()
    tool.name = "test_tool"
    tool.description = "A test tool"
    tool.schema = {
        "type": "object",
        "properties": {
            "input": {"type": "string"}
        },
        "required": ["input"],
    }
    tool.execute = MagicMock(return_value="Tool result")
    return tool


@pytest.fixture
def mock_tool_registry():
    """Mock tool registry."""
    registry = MagicMock()
    registry.register = MagicMock()
    registry.get_tool = MagicMock(return_value=MagicMock())
    registry.list_tools = MagicMock(return_value=[])
    registry.get_schema = MagicMock(return_value={})
    return registry


# =============================================================================
# MOCK REASONING ENGINE FIXTURES
# =============================================================================

@pytest.fixture
def mock_reasoning_engine():
    """Mock reasoning engine."""
    engine = AsyncMock()
    engine.reason = AsyncMock(return_value="Reasoning result")
    engine.chain_of_thought = AsyncMock(return_value=["Step 1", "Step 2", "Step 3"])
    engine.self_consistency = AsyncMock(return_value={
        "result": "Final result",
        "confidence": 0.95,
        "paths": 3,
    })
    return engine


# =============================================================================
# MOCK UCF FIXTURES
# =============================================================================

@pytest.fixture
def mock_ucf_metrics():
    """Mock UCF metrics."""
    metrics = {
        "zoom": 0.5,
        "harmony": 0.8,
        "resilience": 0.7,
        "prana": 0.6,
        "drishti": 0.9,
        "klesha": 0.2,
    }
    return metrics


@pytest.fixture
def mock_ucf_adapter():
    """Mock UCF adapter."""
    adapter = AsyncMock()
    adapter.collect_metrics = AsyncMock(return_value={
        "zoom": 0.5,
        "harmony": 0.8,
        "resilience": 0.7,
        "prana": 0.6,
        "drishti": 0.9,
        "klesha": 0.2,
    })
    adapter.update_state = AsyncMock()
    adapter.get_state = AsyncMock(return_value={})
    return adapter


# =============================================================================
# MOCK CONTEXT FIXTURES
# =============================================================================

@pytest.fixture
def mock_context():
    """Mock execution context."""
    context = MagicMock()
    context.state = {}
    context.metadata = {}
    context.get = MagicMock(return_value=None)
    context.set = MagicMock()
    context.update = MagicMock()
    return context


@pytest.fixture
def mock_message_bus():
    """Mock message bus."""
    bus = AsyncMock()
    bus.publish = AsyncMock()
    bus.subscribe = MagicMock()
    bus.unsubscribe = MagicMock()
    bus.emit = AsyncMock()
    return bus


# =============================================================================
# MOCK RUNTIME FIXTURES
# =============================================================================

@pytest.fixture
def mock_runtime():
    """Mock runtime."""
    runtime = AsyncMock()
    runtime.initialize = AsyncMock()
    runtime.shutdown = AsyncMock()
    runtime.execute = AsyncMock(return_value="Execution result")
    runtime.get_status = MagicMock(return_value="running")
    return runtime


# =============================================================================
# TEST DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_prompt():
    """Sample prompt for testing."""
    return "What is the capital of France?"


@pytest.fixture
def sample_tool_definition():
    """Sample tool definition."""
    return {
        "name": "calculator",
        "description": "Perform mathematical calculations",
        "parameters": {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Mathematical expression to evaluate",
                }
            },
            "required": ["expression"],
        },
    }


@pytest.fixture
def sample_reasoning_config():
    """Sample reasoning configuration."""
    return {
        "method": "chain_of_thought",
        "max_steps": 10,
        "temperature": 0.7,
        "top_p": 0.9,
    }


@pytest.fixture
def sample_ucf_config():
    """Sample UCF configuration."""
    return {
        "zoom_target": 0.5,
        "harmony_target": 0.8,
        "resilience_target": 0.7,
        "prana_target": 0.6,
        "drishti_target": 0.9,
        "klesha_target": 0.2,
    }


# =============================================================================
# PERFORMANCE TESTING FIXTURES
# =============================================================================

@pytest.fixture
def performance_timer():
    """Timer for performance testing."""
    class Timer:
        def __init__(self):
            self.start_time = None
            self.end_time = None

        def start(self):
            self.start_time = asyncio.get_event_loop().time()

        def stop(self):
            self.end_time = asyncio.get_event_loop().time()

        @property
        def elapsed(self):
            if self.start_time and self.end_time:
                return self.end_time - self.start_time
            return None

    return Timer()


@pytest.fixture
def memory_tracker():
    """Track memory usage."""
    import tracemalloc

    class MemoryTracker:
        def __init__(self):
            self.start_memory = None
            self.end_memory = None

        def start(self):
            tracemalloc.start()
            self.start_memory = tracemalloc.get_traced_memory()[0]

        def stop(self):
            self.end_memory = tracemalloc.get_traced_memory()[0]
            tracemalloc.stop()

        @property
        def delta(self):
            if self.start_memory and self.end_memory:
                return (self.end_memory - self.start_memory) / 1024 / 1024
            return None

    return MemoryTracker()


# =============================================================================
# CLEANUP FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def cleanup():
    """Cleanup after each test."""
    yield
    # Cleanup logic here
    asyncio.sleep(0)


# =============================================================================
# PARAMETRIZE FIXTURES
# =============================================================================

@pytest.fixture(params=["openai", "anthropic", "local"])
def llm_provider_type(request):
    """Parametrized LLM provider types."""
    return request.param


@pytest.fixture(params=["chain_of_thought", "self_consistency", "tree_of_thought"])
def reasoning_method(request):
    """Parametrized reasoning methods."""
    return request.param


# =============================================================================
# TEMPORARY FILE FIXTURES
# =============================================================================

@pytest.fixture
def temp_config_file(tmp_path):
    """Create a temporary config file."""
    config = {
        "llm": {
            "provider": "openai",
            "model": "gpt-4",
            "temperature": 0.7,
        },
        "reasoning": {
            "method": "chain_of_thought",
            "max_steps": 10,
        },
        "tools": {
            "enabled": True,
            "timeout": 30,
        },
    }
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    return config_file


@pytest.fixture
def temp_state_file(tmp_path):
    """Create a temporary state file."""
    state = {
        "status": "initialized",
        "agents": [],
        "metrics": {},
    }
    state_file = tmp_path / "state.json"
    state_file.write_text(json.dumps(state))
    return state_file


# =============================================================================
# ASSERTION HELPERS
# =============================================================================

class AssertionHelpers:
    """Helper methods for assertions."""

    @staticmethod
    def assert_valid_response(response: Dict[str, Any]):
        """Assert response has valid structure."""
        assert isinstance(response, dict)
        assert "status" in response or "result" in response

    @staticmethod
    def assert_valid_metrics(metrics: Dict[str, float]):
        """Assert metrics are valid."""
        assert isinstance(metrics, dict)
        for key, value in metrics.items():
            assert isinstance(value, (int, float))
            assert 0 <= value <= 1, f"{key} must be between 0 and 1"

    @staticmethod
    def assert_valid_schema(schema: Dict[str, Any]):
        """Assert schema is valid."""
        assert isinstance(schema, dict)
        assert "type" in schema
        assert "properties" in schema or "items" in schema


@pytest.fixture
def assertion_helpers():
    """Provide assertion helpers."""
    return AssertionHelpers()


# =============================================================================
# MOCK DATA GENERATORS
# =============================================================================

class MockDataGenerator:
    """Generate mock data for testing."""

    @staticmethod
    def generate_llm_response(text: str = "Test response") -> Dict[str, Any]:
        """Generate mock LLM response."""
        return {
            "id": "test-response",
            "object": "text_completion",
            "created": 1234567890,
            "model": "gpt-4",
            "choices": [{"text": text, "finish_reason": "stop", "index": 0}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 15, "total_tokens": 25},
        }

    @staticmethod
    def generate_tool_execution(result: str = "Success") -> Dict[str, Any]:
        """Generate mock tool execution result."""
        return {
            "tool": "test_tool",
            "status": "success",
            "result": result,
            "duration_ms": 100,
        }

    @staticmethod
    def generate_reasoning_chain(steps: int = 3) -> List[str]:
        """Generate mock reasoning chain."""
        return [f"Step {i+1}: Reasoning step" for i in range(steps)]


@pytest.fixture
def mock_data_generator():
    """Provide mock data generator."""
    return MockDataGenerator()
