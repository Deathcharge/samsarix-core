# Getting Started with Helix-Core

**Quick start guide for Helix-Core framework**

---

## Installation

### From PyPI

```bash
pip install helix-core
```

### From Source

```bash
git clone https://github.com/Deathcharge/helix-core.git
cd helix-core
pip install -e .
```

### Development Installation

```bash
pip install -e ".[dev]"
```

---

## Quick Start

### 1. Basic Text Generation

```python
import asyncio
from helix_core import HelixRuntime

async def main():
    runtime = HelixRuntime()
    await runtime.initialize()
    
    result = await runtime.llm_bridge.generate(
        "What is machine learning?"
    )
    print(result)
    
    await runtime.shutdown()

asyncio.run(main())
```

### 2. Using Tools

```python
from helix_core import Tool, HelixRuntime

@Tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    return str(eval(expression))

async def main():
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Register tool
    runtime.tool_registry.register(calculate)
    
    # Execute tool
    result = await runtime.tool_executor.execute(
        "calculate",
        expression="10 * 5"
    )
    print(f"Result: {result}")
    
    await runtime.shutdown()

asyncio.run(main())
```

### 3. Reasoning

```python
async def main():
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Chain-of-thought reasoning
    result = await runtime.reasoning.reason(
        "If I have 10 apples and eat 3, how many do I have?"
    )
    print(f"Result: {result}")
    
    await runtime.shutdown()

asyncio.run(main())
```

---

## Core Concepts

### HelixRuntime

The main entry point for all Helix-Core functionality.

```python
runtime = HelixRuntime()
await runtime.initialize()

# Use runtime components
result = await runtime.llm_bridge.generate("prompt")

await runtime.shutdown()
```

### LLM Bridge

Unified interface for multiple LLM providers.

```python
# Generate text
result = await runtime.llm_bridge.generate("prompt")

# Stream text
async for chunk in await runtime.llm_bridge.stream("prompt"):
    print(chunk, end="")

# Count tokens
tokens = runtime.llm_bridge.count_tokens("text")

# Estimate cost
cost = runtime.llm_bridge.estimate_cost("prompt")
```

### Tool System

Define and execute tools.

```python
# Define tool
@Tool
def my_tool(param: str) -> str:
    """Tool description"""
    return f"Result: {param}"

# Register
runtime.tool_registry.register(my_tool)

# Execute
result = await runtime.tool_executor.execute("my_tool", param="value")
```

### Reasoning Engines

Advanced reasoning capabilities.

```python
# Chain-of-thought
result = await runtime.reasoning.reason("question")

# Self-consistency
result = await runtime.reasoning.self_consistency("question", num_paths=3)
```

---

## Configuration

### Environment Variables

```bash
# LLM Provider
export HELIX_LLM_PROVIDER=openai
export HELIX_LLM_MODEL=gpt-4
export HELIX_LLM_API_KEY=sk-...

# Reasoning
export HELIX_REASONING_METHOD=chain_of_thought
export HELIX_REASONING_MAX_STEPS=10

# UCF
export HELIX_UCF_ENABLED=true
```

### Configuration File

Create `helix_config.yaml`:

```yaml
llm:
  provider: openai
  model: gpt-4
  temperature: 0.7
  max_tokens: 1000

reasoning:
  method: chain_of_thought
  max_steps: 10

tools:
  enabled: true
  timeout: 30

ucf:
  enabled: true
  metrics:
    - zoom
    - harmony
    - resilience
```

---

## Common Patterns

### Error Handling

```python
try:
    result = await runtime.llm_bridge.generate("prompt")
except LLMProviderError as e:
    print(f"LLM error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

### Batch Processing

```python
prompts = ["Prompt 1", "Prompt 2", "Prompt 3"]
results = await runtime.llm_bridge.batch_generate(prompts)
```

### Token Management

```python
# Count tokens before API call
tokens = runtime.llm_bridge.count_tokens(prompt)
if tokens > 8000:
    prompt = prompt[:4000]  # Truncate

# Estimate cost
cost = runtime.llm_bridge.estimate_cost(prompt)
print(f"Estimated cost: ${cost:.4f}")
```

### Context Management

```python
# Set context
runtime.context.set("agent_id", "agent_001")
runtime.context.set("task", "answer_questions")

# Get context
agent_id = runtime.context.get("agent_id")
task = runtime.context.get("task", "default")
```

---

## Troubleshooting

### Issue: "API Key not found"

**Solution**: Set environment variable:
```bash
export HELIX_LLM_API_KEY=sk-...
```

### Issue: "Tool not found"

**Solution**: Register tool before execution:
```python
runtime.tool_registry.register(my_tool)
```

### Issue: "Token limit exceeded"

**Solution**: Count tokens and truncate:
```python
tokens = runtime.llm_bridge.count_tokens(prompt)
if tokens > max_tokens:
    prompt = prompt[:max_tokens * 4]  # Rough estimate
```

### Issue: "Timeout error"

**Solution**: Increase timeout or use streaming:
```python
# Streaming (no timeout)
async for chunk in await runtime.llm_bridge.stream(prompt):
    print(chunk, end="")
```

---

## Next Steps

1. **Explore Examples**: See `examples/` directory
2. **Read API Reference**: See `docs/API_REFERENCE.md`
3. **Check Best Practices**: See `docs/BEST_PRACTICES.md`
4. **Review Architecture**: See `docs/ARCHITECTURE.md`

---

## Resources

- **Documentation**: [docs/](../docs/)
- **Examples**: [examples/](../examples/)
- **API Reference**: [docs/API_REFERENCE.md](./API_REFERENCE.md)
- **Contributing**: [CONTRIBUTING.md](../CONTRIBUTING.md)
- **Issues**: [GitHub Issues](https://github.com/Deathcharge/helix-core/issues)

---

## Support

- **Community**: GitHub Discussions
- **Issues**: GitHub Issues
- **Email**: support@helixcollective.io

---

**Happy coding with Helix-Core! 🚀**
