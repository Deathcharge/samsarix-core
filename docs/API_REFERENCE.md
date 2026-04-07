# Helix-Core API Reference

**Complete API documentation for helix-core framework**

---

## Table of Contents

1. [LLM Bridge](#llm-bridge)
2. [Reasoning Engines](#reasoning-engines)
3. [Tool System](#tool-system)
4. [UCF Integration](#ucf-integration)
5. [Core Components](#core-components)
6. [Exceptions](#exceptions)

---

## LLM Bridge

The LLM Bridge provides a unified interface for multiple LLM providers with support for streaming, batching, token counting, and cost estimation.

### HelixCoreLLMBridge

Main class for LLM integration.

#### Methods

##### `async generate(prompt: str, **kwargs) -> str`

Generate text from a prompt.

**Parameters**:
- `prompt` (str): The input prompt
- `model` (str, optional): Model to use
- `temperature` (float, optional): Sampling temperature (0-1)
- `max_tokens` (int, optional): Maximum tokens to generate
- `top_p` (float, optional): Nucleus sampling parameter
- `system_prompt` (str, optional): System prompt for context
- `provider` (str, optional): Specific provider to use

**Returns**:
- str: Generated text

**Example**:
```python
bridge = HelixCoreLLMBridge()
result = await bridge.generate(
    "What is machine learning?",
    temperature=0.7,
    max_tokens=200
)
```

##### `async stream(prompt: str, **kwargs) -> AsyncIterator[str]`

Stream text generation.

**Parameters**:
- `prompt` (str): The input prompt
- `model` (str, optional): Model to use
- `temperature` (float, optional): Sampling temperature
- `max_tokens` (int, optional): Maximum tokens

**Returns**:
- AsyncIterator[str]: Stream of text chunks

**Example**:
```python
async for chunk in await bridge.stream("Tell me a story"):
    print(chunk, end="")
```

##### `count_tokens(text: str, model: str = None) -> int`

Count tokens in text.

**Parameters**:
- `text` (str): Text to count
- `model` (str, optional): Model for counting

**Returns**:
- int: Number of tokens

**Example**:
```python
tokens = bridge.count_tokens("Hello world")
print(f"Token count: {tokens}")
```

##### `estimate_cost(prompt: str, output_tokens: int = 0, model: str = None) -> float`

Estimate cost of API call.

**Parameters**:
- `prompt` (str): Input prompt
- `output_tokens` (int, optional): Expected output tokens
- `model` (str, optional): Model to use

**Returns**:
- float: Estimated cost in USD

**Example**:
```python
cost = bridge.estimate_cost("Test prompt", output_tokens=100)
print(f"Estimated cost: ${cost:.4f}")
```

##### `add_provider(provider: LLMProvider) -> None`

Add a new LLM provider.

**Parameters**:
- `provider` (LLMProvider): Provider instance

**Example**:
```python
from helix_core.llm_providers import OpenAIProvider
provider = OpenAIProvider(api_key="sk-...")
bridge.add_provider(provider)
```

##### `async batch_generate(prompts: List[str], **kwargs) -> List[str]`

Generate text for multiple prompts.

**Parameters**:
- `prompts` (List[str]): List of prompts
- `**kwargs`: Additional parameters

**Returns**:
- List[str]: List of generated texts

**Example**:
```python
prompts = ["What is AI?", "What is ML?"]
results = await bridge.batch_generate(prompts)
```

---

## Reasoning Engines

Advanced reasoning capabilities for complex problem-solving.

### AlgoOfThoughts

Advanced chain-of-thought reasoning engine.

#### Methods

##### `async reason(query: str, tools: List[Tool] = None, max_steps: int = 10) -> str`

Perform chain-of-thought reasoning.

**Parameters**:
- `query` (str): The question or task
- `tools` (List[Tool], optional): Available tools
- `max_steps` (int, optional): Maximum reasoning steps

**Returns**:
- str: Final reasoning result

**Example**:
```python
reasoning = AlgoOfThoughts()
result = await reasoning.reason(
    "What is 2 + 2?",
    max_steps=5
)
```

##### `async get_chain() -> List[str]`

Get the reasoning chain.

**Returns**:
- List[str]: Steps in the reasoning chain

**Example**:
```python
chain = await reasoning.get_chain()
for i, step in enumerate(chain, 1):
    print(f"Step {i}: {step}")
```

### SelfConsistency

Multiple reasoning paths for robust outputs.

#### Methods

##### `async reason(query: str, num_paths: int = 3) -> Dict[str, Any]`

Generate multiple reasoning paths.

**Parameters**:
- `query` (str): The question
- `num_paths` (int, optional): Number of paths to generate

**Returns**:
- Dict with 'result', 'confidence', and 'paths'

**Example**:
```python
consistency = SelfConsistency()
result = await consistency.reason("Is AI dangerous?", num_paths=5)
print(f"Result: {result['result']}")
print(f"Confidence: {result['confidence']:.2%}")
```

---

## Tool System

Declarative tool definition and execution.

### Tool Decorator

Define a tool using the decorator.

**Example**:
```python
from helix_core import Tool

@Tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    return str(eval(expression))

@Tool
def search(query: str) -> str:
    """Search the web"""
    return f"Results for: {query}"
```

### ToolRegistry

Manage tools.

#### Methods

##### `register(tool: Tool) -> None`

Register a tool.

**Parameters**:
- `tool` (Tool): Tool to register

**Example**:
```python
registry = ToolRegistry()
registry.register(calculate)
registry.register(search)
```

##### `get_tool(name: str) -> Tool`

Get a tool by name.

**Parameters**:
- `name` (str): Tool name

**Returns**:
- Tool: The tool

**Example**:
```python
tool = registry.get_tool("calculate")
```

##### `list_tools() -> List[str]`

List all registered tools.

**Returns**:
- List[str]: Tool names

**Example**:
```python
tools = registry.list_tools()
print(f"Available tools: {', '.join(tools)}")
```

### ToolExecutor

Execute tools.

#### Methods

##### `async execute(tool_name: str, **kwargs) -> Any`

Execute a tool.

**Parameters**:
- `tool_name` (str): Name of tool to execute
- `**kwargs`: Tool parameters

**Returns**:
- Any: Tool result

**Example**:
```python
executor = ToolExecutor(registry)
result = await executor.execute("calculate", expression="2 + 2")
print(f"Result: {result}")
```

---

## UCF Integration

Universal Consciousness Framework integration.

### UCFAdapter

Adapt to UCF metrics.

#### Methods

##### `async collect_metrics() -> Dict[str, float]`

Collect UCF metrics.

**Returns**:
- Dict with metrics: zoom, harmony, resilience, prana, drishti, klesha

**Example**:
```python
adapter = UCFAdapter()
metrics = await adapter.collect_metrics()
print(f"Harmony: {metrics['harmony']:.2f}")
```

##### `async update_state(state: Dict[str, Any]) -> None`

Update UCF state.

**Parameters**:
- `state` (Dict): State to update

**Example**:
```python
await adapter.update_state({
    "agents": 5,
    "status": "active"
})
```

---

## Core Components

### HelixRuntime

Main runtime for orchestration.

#### Methods

##### `async initialize() -> None`

Initialize the runtime.

**Example**:
```python
runtime = HelixRuntime()
await runtime.initialize()
```

##### `async execute_flow(flow: Dict, inputs: Dict) -> Any`

Execute a flow.

**Parameters**:
- `flow` (Dict): Flow definition
- `inputs` (Dict): Input data

**Returns**:
- Any: Flow result

**Example**:
```python
flow = {
    "steps": [
        {"type": "generate", "prompt": "Hello"},
        {"type": "reason", "query": "What does this mean?"}
    ]
}
result = await runtime.execute_flow(flow, {})
```

### Context

Manage execution context.

#### Methods

##### `get(key: str, default: Any = None) -> Any`

Get context value.

**Parameters**:
- `key` (str): Key to retrieve
- `default` (Any, optional): Default value

**Returns**:
- Any: Context value

**Example**:
```python
value = context.get("agent_id", "unknown")
```

##### `set(key: str, value: Any) -> None`

Set context value.

**Parameters**:
- `key` (str): Key to set
- `value` (Any): Value to set

**Example**:
```python
context.set("agent_id", "agent_1")
```

### MessageBus

Inter-component communication.

#### Methods

##### `async publish(event: str, data: Dict) -> None`

Publish an event.

**Parameters**:
- `event` (str): Event name
- `data` (Dict): Event data

**Example**:
```python
await bus.publish("agent_ready", {"agent_id": "agent_1"})
```

##### `subscribe(event: str, handler: Callable) -> None`

Subscribe to an event.

**Parameters**:
- `event` (str): Event name
- `handler` (Callable): Handler function

**Example**:
```python
def on_agent_ready(data):
    print(f"Agent ready: {data['agent_id']}")

bus.subscribe("agent_ready", on_agent_ready)
```

---

## Exceptions

Custom exceptions for error handling.

### HelixCoreException

Base exception for helix-core.

```python
try:
    result = await bridge.generate("test")
except HelixCoreException as e:
    print(f"Error: {e}")
```

### LLMProviderError

Error from LLM provider.

```python
try:
    result = await bridge.generate("test")
except LLMProviderError as e:
    print(f"Provider error: {e}")
```

### ToolExecutionError

Error executing a tool.

```python
try:
    result = await executor.execute("tool_name")
except ToolExecutionError as e:
    print(f"Tool error: {e}")
```

### ValidationError

Validation error.

```python
try:
    schema = tool.get_schema()
except ValidationError as e:
    print(f"Validation error: {e}")
```

---

## Best Practices

### 1. Error Handling

Always handle exceptions:

```python
try:
    result = await bridge.generate("prompt")
except LLMProviderError as e:
    logger.error(f"LLM error: {e}")
    result = await bridge.generate("prompt", provider="fallback")
```

### 2. Resource Management

Use async context managers:

```python
async with HelixRuntime() as runtime:
    result = await runtime.execute_flow(flow, inputs)
```

### 3. Token Counting

Count tokens before API calls:

```python
tokens = bridge.count_tokens(prompt)
if tokens > 8000:
    prompt = prompt[:4000]  # Truncate
```

### 4. Cost Estimation

Estimate costs before large batches:

```python
cost = bridge.estimate_cost(prompt, output_tokens=1000)
if cost > budget:
    logger.warning(f"Cost {cost} exceeds budget {budget}")
```

### 5. Tool Validation

Validate tools before execution:

```python
schema = tool.get_schema()
if not validate_schema(schema):
    raise ValidationError("Invalid tool schema")
```

---

## Examples

### Complete Workflow

```python
import asyncio
from helix_core import HelixRuntime, Tool

@Tool
def calculate(expression: str) -> str:
    return str(eval(expression))

async def main():
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Generate text
    result = await runtime.llm_bridge.generate(
        "What is 2 + 2?"
    )
    print(f"LLM: {result}")
    
    # Reason about it
    reasoning = await runtime.reasoning.reason(
        "Verify that 2 + 2 = 4"
    )
    print(f"Reasoning: {reasoning}")
    
    await runtime.shutdown()

asyncio.run(main())
```

### Tool-Based Workflow

```python
async def main():
    runtime = HelixRuntime()
    registry = runtime.tool_registry
    registry.register(calculate)
    
    # Execute tool
    result = await runtime.tool_executor.execute(
        "calculate",
        expression="10 * 5"
    )
    print(f"Result: {result}")
```

---

**For more information, see the [README](../README.md) and [Contributing Guide](../CONTRIBUTING.md)**
