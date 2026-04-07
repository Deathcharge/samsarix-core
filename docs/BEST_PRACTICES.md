# Helix-Core Best Practices Guide

**Professional development patterns and recommendations**

---

## Table of Contents

1. [Error Handling](#error-handling)
2. [Resource Management](#resource-management)
3. [Performance Optimization](#performance-optimization)
4. [Security](#security)
5. [Testing](#testing)
6. [Documentation](#documentation)

---

## Error Handling

### 1. Always Handle Exceptions

```python
from helix_core.exceptions import LLMProviderError, ToolExecutionError

try:
    result = await runtime.llm_bridge.generate("prompt")
except LLMProviderError as e:
    logger.error(f"LLM error: {e}")
    # Implement fallback logic
    result = await fallback_generate("prompt")
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    raise
```

### 2. Use Specific Exceptions

```python
# ❌ Bad: Too broad
try:
    result = await runtime.tool_executor.execute("tool")
except Exception:
    pass

# ✅ Good: Specific exceptions
try:
    result = await runtime.tool_executor.execute("tool")
except ToolExecutionError as e:
    logger.error(f"Tool execution failed: {e}")
except ToolNotFoundError as e:
    logger.error(f"Tool not found: {e}")
```

### 3. Implement Retry Logic

```python
from helix_core.features import RetryPolicy

retry_policy = RetryPolicy(
    max_attempts=3,
    initial_delay=1.0,
    backoff_factor=2.0,
)

result = await retry_policy.execute(
    runtime.llm_bridge.generate,
    "prompt"
)
```

### 4. Use Circuit Breaker Pattern

```python
from helix_core.features import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,
    recovery_timeout=60.0,
)

if breaker.can_execute():
    try:
        result = await runtime.llm_bridge.generate("prompt")
        breaker.record_success()
    except Exception as e:
        breaker.record_failure()
        raise
```

---

## Resource Management

### 1. Use Async Context Managers

```python
# ❌ Bad: Manual cleanup
runtime = HelixRuntime()
await runtime.initialize()
try:
    result = await runtime.llm_bridge.generate("prompt")
finally:
    await runtime.shutdown()

# ✅ Good: Context manager
async with HelixRuntime() as runtime:
    result = await runtime.llm_bridge.generate("prompt")
```

### 2. Manage Token Limits

```python
# Count tokens before API call
tokens = runtime.llm_bridge.count_tokens(prompt)

if tokens > 8000:
    # Truncate or split prompt
    prompt = prompt[:4000]
    logger.warning(f"Prompt truncated from {tokens} to {runtime.llm_bridge.count_tokens(prompt)} tokens")
```

### 3. Monitor Memory Usage

```python
import tracemalloc

tracemalloc.start()

# Your code here
result = await runtime.llm_bridge.generate("prompt")

current, peak = tracemalloc.get_traced_memory()
logger.info(f"Memory usage: {current / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

### 4. Clean Up Resources

```python
# Always unregister tools when done
runtime.tool_registry.unregister("tool_name")

# Clear context
runtime.context.clear()

# Clear cache
runtime.cache.clear()
```

---

## Performance Optimization

### 1. Use Batch Processing

```python
# ❌ Bad: Sequential processing
results = []
for prompt in prompts:
    result = await runtime.llm_bridge.generate(prompt)
    results.append(result)

# ✅ Good: Batch processing
results = await runtime.llm_bridge.batch_generate(prompts)
```

### 2. Implement Caching

```python
from helix_core.features import Cache

cache = Cache(
    max_size=1000,
    eviction_policy="lru",
    default_ttl=3600,  # 1 hour
)

# Check cache first
cached = cache.get(prompt)
if cached:
    return cached

# Generate if not cached
result = await runtime.llm_bridge.generate(prompt)
cache.set(prompt, result)
return result
```

### 3. Use Rate Limiting

```python
from helix_core.features import RateLimiter

limiter = RateLimiter(rate=10, burst=20)  # 10 req/sec, burst 20

async def rate_limited_generate(prompt):
    await limiter.acquire()
    return await runtime.llm_bridge.generate(prompt)
```

### 4. Monitor Performance

```python
from helix_core.features import Monitor

monitor = Monitor()

# Time an operation
monitor.start_timer("generation")
result = await runtime.llm_bridge.generate("prompt")
elapsed = monitor.stop_timer("generation")

# Get statistics
stats = monitor.get_statistics("generation")
logger.info(f"Generation stats: {stats}")
```

### 5. Parallel Execution

```python
from helix_core.features import PerformanceOptimizer

optimizer = PerformanceOptimizer()

# Batch items
batches = optimizer.batch_items(items, batch_size=10)

# Execute in parallel
async def process_batch(batch):
    return await runtime.llm_bridge.batch_generate(batch)

results = await optimizer.parallel_execute(
    [process_batch(b) for b in batches],
    max_concurrent=5,
)
```

---

## Security

### 1. Protect API Keys

```python
# ❌ Bad: Hardcoded API key
bridge = HelixCoreLLMBridge(api_key="sk-...")

# ✅ Good: Environment variable
import os
api_key = os.getenv("HELIX_LLM_API_KEY")
bridge = HelixCoreLLMBridge(api_key=api_key)
```

### 2. Validate Input

```python
from helix_core.exceptions import ValidationError

def validate_prompt(prompt):
    if not isinstance(prompt, str):
        raise ValidationError("Prompt must be a string", field="prompt")
    
    if len(prompt) > 10000:
        raise ValidationError("Prompt too long", field="prompt", max_length=10000)
    
    if not prompt.strip():
        raise ValidationError("Prompt cannot be empty", field="prompt")
    
    return prompt

prompt = validate_prompt(user_input)
```

### 3. Sanitize Output

```python
import html

def sanitize_output(text):
    # Remove potentially harmful content
    text = html.escape(text)
    # Remove control characters
    text = ''.join(c for c in text if ord(c) >= 32 or c in '\n\t')
    return text

result = await runtime.llm_bridge.generate("prompt")
safe_result = sanitize_output(result)
```

### 4. Audit Logging

```python
import logging

# Configure audit logger
audit_logger = logging.getLogger("helix_audit")

# Log important operations
audit_logger.info(f"User {user_id} generated text with prompt: {prompt[:100]}...")
audit_logger.info(f"Tool {tool_name} executed with params: {params}")
audit_logger.warning(f"Rate limit exceeded for provider {provider}")
```

---

## Testing

### 1. Unit Test Pattern

```python
import pytest

@pytest.mark.asyncio
async def test_generate_text():
    runtime = HelixRuntime()
    await runtime.initialize()
    
    result = await runtime.llm_bridge.generate("test")
    
    assert isinstance(result, str)
    assert len(result) > 0
    
    await runtime.shutdown()
```

### 2. Mock External Services

```python
from unittest.mock import AsyncMock

@pytest.fixture
def mock_llm_bridge():
    bridge = AsyncMock()
    bridge.generate.return_value = "Mocked response"
    return bridge

@pytest.mark.asyncio
async def test_with_mock(mock_llm_bridge):
    result = await mock_llm_bridge.generate("test")
    assert result == "Mocked response"
```

### 3. Test Error Handling

```python
@pytest.mark.asyncio
async def test_error_handling():
    runtime = HelixRuntime()
    
    with pytest.raises(LLMProviderError):
        await runtime.llm_bridge.generate(None)
```

### 4. Performance Testing

```python
@pytest.mark.slow
@pytest.mark.asyncio
async def test_performance():
    runtime = HelixRuntime()
    
    import time
    start = time.time()
    
    for _ in range(100):
        await runtime.llm_bridge.generate("test")
    
    elapsed = time.time() - start
    assert elapsed < 60  # Should complete in 60 seconds
```

---

## Documentation

### 1. Document Functions

```python
async def generate_with_reasoning(
    prompt: str,
    max_steps: int = 10,
) -> str:
    """Generate text with chain-of-thought reasoning.
    
    This function generates text using the LLM bridge with
    chain-of-thought reasoning for complex queries.
    
    Args:
        prompt: The input prompt for generation
        max_steps: Maximum reasoning steps (default: 10)
    
    Returns:
        Generated text with reasoning
    
    Raises:
        LLMProviderError: If LLM provider fails
        ValidationError: If prompt is invalid
    
    Example:
        >>> result = await generate_with_reasoning(
        ...     "What is 2 + 2?",
        ...     max_steps=5
        ... )
        >>> print(result)
    """
    # Implementation
    pass
```

### 2. Add Type Hints

```python
from typing import List, Dict, Optional, Union

async def batch_generate(
    prompts: List[str],
    temperature: Optional[float] = None,
    max_tokens: Union[int, None] = None,
) -> List[str]:
    """Generate text for multiple prompts."""
    pass
```

### 3. Document Exceptions

```python
async def execute_tool(tool_name: str) -> Any:
    """Execute a tool.
    
    Raises:
        ToolNotFoundError: If tool is not registered
        ToolExecutionError: If tool execution fails
        ToolTimeoutError: If tool execution times out
    """
    pass
```

---

## Common Patterns

### Workflow Pattern

```python
async def complete_workflow(query: str) -> Dict[str, Any]:
    """Complete workflow with error handling."""
    
    async with HelixRuntime() as runtime:
        try:
            # Validate input
            query = validate_prompt(query)
            
            # Generate response
            response = await runtime.llm_bridge.generate(query)
            
            # Reason about response
            reasoning = await runtime.reasoning.reason(query)
            
            # Return results
            return {
                "query": query,
                "response": response,
                "reasoning": reasoning,
            }
        
        except LLMProviderError as e:
            logger.error(f"LLM error: {e}")
            return {"error": "Generation failed", "details": str(e)}
        
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
```

### Agent Pattern

```python
class Agent:
    """Intelligent agent using Helix-Core."""
    
    def __init__(self, runtime: HelixRuntime):
        self.runtime = runtime
        self.memory = []
        self.tools = {}
    
    async def think(self, query: str) -> str:
        """Think about a query."""
        return await self.runtime.reasoning.reason(query)
    
    async def act(self, action: str) -> Any:
        """Execute an action."""
        return await self.runtime.tool_executor.execute(action)
    
    async def observe(self, observation: str) -> None:
        """Observe and remember."""
        self.memory.append(observation)
```

---

## Performance Checklist

- ✅ Use batch processing for multiple items
- ✅ Implement caching for repeated queries
- ✅ Monitor token usage and costs
- ✅ Use rate limiting for API calls
- ✅ Implement retry logic with backoff
- ✅ Use circuit breakers for fault tolerance
- ✅ Profile code for bottlenecks
- ✅ Test performance with benchmarks

---

## Security Checklist

- ✅ Never hardcode API keys
- ✅ Validate all user input
- ✅ Sanitize output before displaying
- ✅ Use HTTPS for all connections
- ✅ Implement audit logging
- ✅ Rotate API keys regularly
- ✅ Use environment variables for secrets
- ✅ Implement rate limiting

---

## Troubleshooting

### Issue: High Memory Usage

**Solution**: Implement caching with TTL and eviction policies

```python
cache = Cache(max_size=100, default_ttl=3600)
```

### Issue: Slow Generation

**Solution**: Use batch processing and parallel execution

```python
results = await runtime.llm_bridge.batch_generate(prompts)
```

### Issue: Rate Limiting

**Solution**: Implement rate limiter and retry policy

```python
limiter = RateLimiter(rate=10)
retry_policy = RetryPolicy(max_attempts=3)
```

---

**For more information, see [API Reference](./API_REFERENCE.md) and [Getting Started](./GETTING_STARTED.md)**
