# Helix Core Framework

**Foundational utilities for LLM integration, reasoning, and autonomous tool execution**

The core framework that powers Helix's intelligent agent capabilities. Provides LLM bridges, advanced reasoning engines, tool registry systems, and UCF consciousness metrics integration.

## 🎯 Features

### LLM Bridge
- Multi-model support (OpenAI, Anthropic, local models)
- Streaming and batch processing
- Token counting and cost estimation
- Error handling and retry logic

### Reasoning Engines
- **Algo of Thoughts** - Advanced chain-of-thought reasoning
- **Self-Consistency** - Multiple reasoning paths for robust outputs
- Extensible reasoning framework

### Tool System
- Decorator-based tool registration
- Automatic schema generation
- Type validation and error handling
- Tool execution engine

### UCF Integration
- Consciousness metrics tracking
- State management and persistence
- Adapter for external systems
- Real-time metrics collection

### Core Components
- Context management
- Message bus for inter-component communication
- Execution engine
- Runtime management

## 📦 Installation

```bash
pip install helix-core
```

## 🚀 Quick Start

```python
from helix_core import HelixCore, Tool

# Initialize core
core = HelixCore()

# Define a tool
@Tool
def calculate(expression: str) -> str:
    """Evaluate a mathematical expression"""
    return str(eval(expression))

# Use with reasoning
result = core.reason(
    "What is 2 + 2?",
    tools=[calculate]
)
```

## 📊 Statistics

- **Lines of Code**: 4,339
- **Modules**: 8 core modules
- **Python Files**: 22 files
- **Dependencies**: Minimal, production-ready

## 🏗️ Architecture

```
helix_core/
├── core/                    # Core components
│   ├── base.py             # Base classes
│   ├── context.py          # Context management
│   ├── execution.py        # Execution engine
│   ├── message_bus.py      # Inter-component communication
│   ├── orchestrator.py     # Orchestration logic
│   └── runtime.py          # Runtime management
├── reasoning/              # Reasoning engines
│   ├── algo_of_thoughts.py # Advanced CoT reasoning
│   └── self_consistency.py # Multiple reasoning paths
├── tools/                  # Tool system
│   ├── decorator.py        # Tool decorators
│   ├── executor.py         # Tool execution
│   └── registry.py         # Tool registry
├── ucf/                    # UCF integration
│   ├── adapter.py          # UCF adapter
│   ├── metrics.py          # Metrics collection
│   └── store.py            # State storage
├── llm_bridge.py           # LLM integration
├── adapter.py              # External adapters
└── __init__.py             # Package initialization
```

## 🔧 Core Modules

### LLM Bridge
Unified interface for multiple LLM providers with streaming, batching, and cost tracking.

### Reasoning Engines
Advanced reasoning capabilities including chain-of-thought, self-consistency, and custom reasoning strategies.

### Tool Registry
Declarative tool definition and automatic schema generation for LLM integration.

### UCF Adapter
Integration with the Universal Consciousness Framework for metrics tracking and state management.

### Context Manager
Manages execution context, state, and information flow between components.

### Message Bus
Enables loose coupling between components through event-driven communication.

## 📚 Documentation

- [LLM Bridge Guide](./docs/llm_bridge.md)
- [Reasoning Engines](./docs/reasoning.md)
- [Tool System](./docs/tools.md)
- [UCF Integration](./docs/ucf.md)
- [API Reference](./docs/api.md)

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](./CONTRIBUTING.md) for guidelines.

## 📄 License

Dual licensed under:
- **Apache License 2.0** - For open-source use (free)
- **Proprietary Commercial License** - For businesses ($99-999/year)

See [LICENSING.md](./LICENSING.md) for details.

## 🙋 Support

- **Open Source**: Community support via GitHub issues
- **Commercial**: Priority email support (licensing@helixcollective.io)

---

**Built with ❤️ as part of the Helix Collective**
