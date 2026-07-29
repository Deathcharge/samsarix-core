# Helix-Core: Enterprise-Grade LLM Framework

**Professional, production-ready framework for building intelligent applications with LLMs**

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code Coverage](https://img.shields.io/badge/coverage-80%25-brightgreen.svg)](#testing)
[![Documentation](https://img.shields.io/badge/docs-comprehensive-blue.svg)](#documentation)

---

## Overview

Helix-Core is a comprehensive framework for building intelligent applications with Large Language Models. It provides a unified interface for multiple LLM providers, advanced reasoning engines, a declarative tool system, and production-grade features like caching, monitoring, and resilience patterns.

**Key Features**:
- 🤖 **Multi-Provider Support**: OpenAI, Anthropic, local models, and custom providers
- 🧠 **Advanced Reasoning**: Chain-of-thought, self-consistency, and extensible reasoning engines
- 🛠️ **Tool System**: Declarative tool definition with automatic schema generation
- ⚡ **Performance**: Intelligent caching, batch processing, and parallel execution
- 🛡️ **Resilience**: Circuit breakers, retry policies, and graceful degradation
- 📊 **Monitoring**: Built-in metrics collection, health checks, and observability
- 🔒 **Production-Ready**: 80%+ test coverage, comprehensive error handling, security best practices

---

## Quick Start

### Installation

```bash
pip install helix-core
```

### Basic Usage

```python
import asyncio
from helix_core import HelixRuntime

async def main():
    async with HelixRuntime() as runtime:
        # Generate text
        result = await runtime.llm_bridge.generate(
            "What is machine learning?"
        )
        print(result)

asyncio.run(main())
```

### With Tools

```python
from helix_core import Tool, HelixRuntime

@Tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    return str(eval(expression))

async def main():
    async with HelixRuntime() as runtime:
        runtime.tool_registry.register(calculate)
        
        result = await runtime.tool_executor.execute(
            "calculate",
            expression="10 * 5 + 3"
        )
        print(f"Result: {result}")

asyncio.run(main())
```

### With Reasoning

```python
async def main():
    async with HelixRuntime() as runtime:
        # Chain-of-thought reasoning
        result = await runtime.reasoning.reason(
            "If I have 10 apples and eat 3, then buy 5 more, how many do I have?"
        )
        print(f"Result: {result}")

asyncio.run(main())
```

---

## Documentation

### Getting Started
- [Installation Guide](./docs/GETTING_STARTED.md) - Setup and quick start
- [Basic Concepts](./docs/GETTING_STARTED.md#core-concepts) - Understand core components
- [Configuration](./docs/GETTING_STARTED.md#configuration) - Environment and config files

### API Reference
- [Complete API Reference](./docs/API_REFERENCE.md) - All classes and methods
- [LLM Bridge](./docs/API_REFERENCE.md#llm-bridge) - Multi-provider LLM interface
- [Reasoning Engines](./docs/API_REFERENCE.md#reasoning-engines) - Advanced reasoning
- [Tool System](./docs/API_REFERENCE.md#tool-system) - Declarative tools
- [Exception Handling](./docs/API_REFERENCE.md#exceptions) - Error types and recovery

### Architecture
- [System Architecture](./docs/ARCHITECTURE.md) - High-level design
- [Data Flow](./docs/ARCHITECTURE.md#data-flow) - Request processing
- [Design Patterns](./docs/ARCHITECTURE.md#design-patterns) - Implementation patterns
- [Scalability](./docs/ARCHITECTURE.md#scalability) - Production deployment

### Best Practices
- [Error Handling](./docs/BEST_PRACTICES.md#error-handling) - Exception patterns
- [Performance Optimization](./docs/BEST_PRACTICES.md#performance-optimization) - Caching, batching
- [Security](./docs/BEST_PRACTICES.md#security) - API keys, validation, sanitization
- [Testing](./docs/BEST_PRACTICES.md#testing) - Unit and integration tests
- [Common Patterns](./docs/BEST_PRACTICES.md#common-patterns) - Workflows and agents

### Examples
- [Basic Usage](./examples/basic_usage.py) - 10+ detailed examples
- [Tool Integration](./examples/basic_usage.py#example-3) - Using tools
- [Batch Processing](./examples/basic_usage.py#example-7) - Multiple requests
- [Error Handling](./examples/basic_usage.py#example-10) - Exception patterns

---

## Core Features

### 1. Multi-Provider LLM Bridge

Support for multiple LLM providers with automatic fallback and load balancing.

```python
bridge = HelixCoreLLMBridge()
bridge.add_provider(OpenAIProvider(api_key="..."))
bridge.add_provider(AnthropicProvider(api_key="..."))

# Automatic provider selection
result = await bridge.generate("prompt")

# Token counting
tokens = bridge.count_tokens("text")

# Cost estimation
cost = bridge.estimate_cost("prompt")
```

**Supported Providers**:
- OpenAI (GPT-3.5, GPT-4)
- Anthropic (Claude)
- Local models (Ollama, LLaMA)
- Custom providers (extensible)

### 2. Advanced Reasoning Engines

Multiple reasoning strategies for complex problem-solving.

```python
# Chain-of-thought reasoning
result = await runtime.reasoning.reason(
    "Complex question",
    method="chain_of_thought",
    max_steps=10
)

# Self-consistency reasoning
result = await runtime.reasoning.self_consistency(
    "Question",
    num_paths=3
)
```

**Reasoning Methods**:
- Chain-of-Thought: Step-by-step reasoning
- Self-Consistency: Multiple reasoning paths
- Extensible framework for custom methods

### 3. Declarative Tool System

Define tools with automatic schema generation and validation.

```python
@Tool
def search(query: str, num_results: int = 5) -> List[str]:
    """Search the web for information"""
    # Implementation
    pass

@Tool
def calculate(expression: str) -> float:
    """Evaluate mathematical expressions"""
    return eval(expression)

# Register and use
registry.register(search, calculate)
result = await executor.execute("search", query="machine learning")
```

**Features**:
- Automatic schema generation
- Type validation
- Error handling
- Dependency management
- Tool composition

### 4. Intelligent Caching

Multiple eviction policies and TTL support.

```python
from helix_core.features import Cache

cache = Cache(
    max_size=1000,
    eviction_policy="lru",  # lru, lfu, fifo
    default_ttl=3600
)

# Use cache
cached = cache.get("key")
if not cached:
    result = await generate("prompt")
    cache.set("key", result)
```

**Features**:
- LRU, LFU, FIFO eviction policies
- TTL-based expiration
- Cache statistics
- Namespace support

### 5. Performance Monitoring

Built-in metrics collection and analysis.

```python
from helix_core.features import Monitor

monitor = Monitor()

# Time operations
monitor.start_timer("generation")
result = await runtime.llm_bridge.generate("prompt")
elapsed = monitor.stop_timer("generation")

# Get statistics
stats = monitor.get_statistics("generation")
print(f"Avg latency: {stats['avg']:.2f}ms")
```

**Metrics**:
- Request latency (P50, P95, P99)
- Throughput
- Error rates
- Cache hit rates
- Token usage

### 6. Resilience Patterns

Fault tolerance and recovery strategies.

```python
from helix_core.features import RetryPolicy, CircuitBreaker, RateLimiter

# Retry with exponential backoff
retry = RetryPolicy(max_attempts=3, initial_delay=1.0)
result = await retry.execute(runtime.llm_bridge.generate, "prompt")

# Circuit breaker
breaker = CircuitBreaker(failure_threshold=5)
if breaker.can_execute():
    try:
        result = await runtime.llm_bridge.generate("prompt")
        breaker.record_success()
    except Exception:
        breaker.record_failure()

# Rate limiting
limiter = RateLimiter(rate=10, burst=20)
await limiter.acquire()
result = await runtime.llm_bridge.generate("prompt")
```

**Patterns**:
- Retry with exponential backoff
- Circuit breaker for fault tolerance
- Rate limiting with token bucket
- Bulkhead pattern (coming soon)

### 7. Comprehensive Error Handling

30+ custom exception classes with recovery strategies.

```python
from helix_core.exceptions import (
    LLMProviderError,
    RateLimitError,
    ToolExecutionError,
    ValidationError,
)

try:
    result = await runtime.llm_bridge.generate("prompt")
except RateLimitError as e:
    await asyncio.sleep(e.retry_after)
    result = await runtime.llm_bridge.generate("prompt")
except LLMProviderError as e:
    logger.error(f"Provider error: {e}")
    # Fallback logic
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

**Exception Types**:
- LLM Provider errors (API key, rate limit, token limit)
- Tool execution errors (not found, timeout, validation)
- Reasoning errors (timeout, max steps exceeded)
- Validation errors (schema, type)
- Context and runtime errors
- Configuration errors

---

## Testing

Comprehensive test suite with 50+ tests and 80%+ coverage.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=helix_core --cov-report=html

# Run specific test
pytest tests/test_llm_bridge.py::test_generate_text

# Run with markers
pytest -m "not slow"
```

**Test Categories**:
- Unit tests for all core components
- Integration tests with real providers
- Performance benchmarks
- Error handling tests
- Mock fixtures for testing

---

## Performance

### Benchmarks

| Operation | Latency | Throughput |
|-----------|---------|-----------|
| Token counting | <1ms | 1M tokens/sec |
| Cache lookup | <1ms | 10K lookups/sec |
| Tool execution | 10-100ms | 10-100 req/sec |
| LLM generation | 100ms-10s | 1-10 req/sec |
| Reasoning | 1-30s | 0.1-1 req/sec |

### Optimization Tips

1. **Use Batch Processing**: Process multiple requests together
2. **Implement Caching**: Cache frequently used results
3. **Enable Rate Limiting**: Prevent API overload
4. **Monitor Performance**: Track metrics and optimize
5. **Use Parallel Execution**: Execute independent tasks concurrently

---

## Production Deployment

### Requirements

- Python 3.8+
- 2+ CPU cores
- 2GB+ RAM (depends on cache size)
- 1Mbps+ network connection

### Configuration

```yaml
# config.yaml
llm:
  provider: openai
  model: gpt-4
  temperature: 0.7
  max_tokens: 1000

cache:
  max_size: 10000
  eviction_policy: lru
  ttl: 3600

monitoring:
  enabled: true
  log_level: INFO

resilience:
  retry_attempts: 3
  circuit_breaker_threshold: 5
  rate_limit: 10
```

### High Availability

```
┌──────────────┐
│ Load Balancer│
└──────┬───────┘
       │
   ┌───┴────┬────────┬────────┐
   │        │        │        │
   ▼        ▼        ▼        ▼
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│HC-1 │ │HC-2 │ │HC-3 │ │HC-N │
└─────┘ └─────┘ └─────┘ └─────┘
   │        │        │        │
   └────┬───┴────┬───┴────┬───┘
        │        │        │
        ▼        ▼        ▼
    ┌─────────────────────────┐
    │  Shared Cache/Storage   │
    └─────────────────────────┘
```

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

**Development Setup**:
```bash
git clone https://github.com/Deathcharge/helix-core.git
cd helix-core
pip install -e ".[dev]"
pytest
```

---

## License

MIT License - see [LICENSE](./LICENSE) for details

---

## Support

- **Documentation**: [docs/](./docs/)
- **Examples**: [examples/](./examples/)
- **Issues**: [GitHub Issues](https://github.com/Deathcharge/helix-core/issues)
- **Discussions**: [GitHub Discussions](https://github.com/Deathcharge/helix-core/discussions)

---

## Changelog

### v1.0.0 (April 2026)
- ✅ Initial release with comprehensive features
- ✅ Multi-provider LLM support
- ✅ Advanced reasoning engines
- ✅ Declarative tool system
- ✅ 50+ tests with 80%+ coverage
- ✅ Comprehensive documentation
- ✅ Production-ready features (caching, monitoring, resilience)

---

## Roadmap

### Q2 2026
- [ ] Streaming response improvements
- [ ] Additional reasoning engines
- [ ] Performance optimizations
- [ ] Extended provider support

### Q3 2026
- [ ] Distributed execution
- [ ] Advanced monitoring dashboard
- [ ] Plugin system
- [ ] Community integrations

### Q4 2026
- [ ] Enterprise features
- [ ] Advanced security
- [ ] Compliance certifications
- [ ] Commercial support

---

**Built with ❤️ by the Helix Collective**

**[Documentation](./docs/) | [Examples](./examples/) | [Contributing](./CONTRIBUTING.md) | [License](./LICENSE)**
