"""
Basic Usage Examples for Helix-Core

Demonstrates fundamental usage patterns for the Helix-Core framework.
"""

import asyncio
import logging
from helix_core import HelixRuntime, Tool

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# EXAMPLE 1: Basic LLM Generation
# =============================================================================

async def example_basic_generation():
    """Example: Basic text generation."""
    print("\n" + "="*60)
    print("EXAMPLE 1: Basic LLM Generation")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Generate text
    prompt = "What is artificial intelligence?"
    result = await runtime.llm_bridge.generate(prompt)
    
    print(f"\nPrompt: {prompt}")
    print(f"Response: {result}")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 2: Token Counting and Cost Estimation
# =============================================================================

async def example_token_counting():
    """Example: Token counting and cost estimation."""
    print("\n" + "="*60)
    print("EXAMPLE 2: Token Counting and Cost Estimation")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    prompt = "Explain machine learning in detail"
    
    # Count tokens
    token_count = runtime.llm_bridge.count_tokens(prompt)
    print(f"\nPrompt: {prompt}")
    print(f"Token count: {token_count}")
    
    # Estimate cost
    cost = runtime.llm_bridge.estimate_cost(prompt, output_tokens=100)
    print(f"Estimated cost (100 output tokens): ${cost:.4f}")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 3: Streaming Generation
# =============================================================================

async def example_streaming():
    """Example: Streaming text generation."""
    print("\n" + "="*60)
    print("EXAMPLE 3: Streaming Generation")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    prompt = "Tell me a short story"
    print(f"\nPrompt: {prompt}")
    print("Response (streaming):")
    print("-" * 40)
    
    # Stream text
    async for chunk in await runtime.llm_bridge.stream(prompt):
        print(chunk, end="", flush=True)
    
    print("\n" + "-" * 40)
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 4: Tool Definition and Registration
# =============================================================================

# Define tools
@Tool
def calculator(expression: str) -> str:
    """Evaluate a mathematical expression.
    
    Args:
        expression: Mathematical expression (e.g., "2 + 2")
    
    Returns:
        Result of the calculation
    """
    try:
        result = eval(expression)
        return f"Result: {result}"
    except Exception as e:
        return f"Error: {str(e)}"


@Tool
def web_search(query: str) -> str:
    """Search the web for information.
    
    Args:
        query: Search query
    
    Returns:
        Search results (simulated)
    """
    return f"Search results for: {query}"


async def example_tools():
    """Example: Using tools."""
    print("\n" + "="*60)
    print("EXAMPLE 4: Tool Definition and Registration")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Register tools
    runtime.tool_registry.register(calculator)
    runtime.tool_registry.register(web_search)
    
    # List tools
    tools = runtime.tool_registry.list_tools()
    print(f"\nRegistered tools: {', '.join(tools)}")
    
    # Execute tool
    result = await runtime.tool_executor.execute(
        "calculator",
        expression="10 * 5 + 3"
    )
    print(f"\nCalculation: 10 * 5 + 3 = {result}")
    
    # Execute another tool
    result = await runtime.tool_executor.execute(
        "web_search",
        query="Python programming"
    )
    print(f"Search: {result}")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 5: Chain-of-Thought Reasoning
# =============================================================================

async def example_reasoning():
    """Example: Chain-of-thought reasoning."""
    print("\n" + "="*60)
    print("EXAMPLE 5: Chain-of-Thought Reasoning")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    query = "If I have 5 apples and give 2 to my friend, how many do I have left?"
    
    print(f"\nQuery: {query}")
    print("\nReasoning chain:")
    print("-" * 40)
    
    # Perform reasoning
    result = await runtime.reasoning.reason(
        query,
        tools=[calculator],
        max_steps=5
    )
    
    print(f"Result: {result}")
    
    # Get reasoning chain
    chain = await runtime.reasoning.get_chain()
    for i, step in enumerate(chain, 1):
        print(f"Step {i}: {step}")
    
    print("-" * 40)
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 6: Self-Consistency Reasoning
# =============================================================================

async def example_self_consistency():
    """Example: Self-consistency reasoning."""
    print("\n" + "="*60)
    print("EXAMPLE 6: Self-Consistency Reasoning")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    query = "Is artificial intelligence dangerous?"
    
    print(f"\nQuery: {query}")
    print("\nGenerating multiple reasoning paths...")
    
    # Perform self-consistency reasoning
    result = await runtime.reasoning.self_consistency(
        query,
        num_paths=3
    )
    
    print(f"\nFinal result: {result['result']}")
    print(f"Confidence: {result['confidence']:.1%}")
    print(f"Number of paths: {result['paths']}")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 7: Batch Processing
# =============================================================================

async def example_batch_processing():
    """Example: Batch processing."""
    print("\n" + "="*60)
    print("EXAMPLE 7: Batch Processing")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    prompts = [
        "What is machine learning?",
        "What is deep learning?",
        "What is neural networks?"
    ]
    
    print(f"\nProcessing {len(prompts)} prompts in batch...")
    
    # Batch generate
    results = await runtime.llm_bridge.batch_generate(prompts)
    
    for prompt, result in zip(prompts, results):
        print(f"\nPrompt: {prompt}")
        print(f"Response: {result[:100]}...")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 8: UCF Metrics Collection
# =============================================================================

async def example_ucf_metrics():
    """Example: UCF metrics collection."""
    print("\n" + "="*60)
    print("EXAMPLE 8: UCF Metrics Collection")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    # Collect metrics
    metrics = await runtime.ucf_adapter.collect_metrics()
    
    print("\nUCF Metrics:")
    print("-" * 40)
    for metric_name, value in metrics.items():
        print(f"{metric_name:12} : {value:.2f}")
    print("-" * 40)
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 9: Context Management
# =============================================================================

async def example_context():
    """Example: Context management."""
    print("\n" + "="*60)
    print("EXAMPLE 9: Context Management")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    context = runtime.context
    
    # Set context values
    context.set("agent_id", "agent_001")
    context.set("task", "answer_questions")
    context.set("max_retries", 3)
    
    print("\nContext values:")
    print(f"Agent ID: {context.get('agent_id')}")
    print(f"Task: {context.get('task')}")
    print(f"Max retries: {context.get('max_retries')}")
    print(f"Unknown key: {context.get('unknown', 'default_value')}")
    
    await runtime.shutdown()


# =============================================================================
# EXAMPLE 10: Error Handling
# =============================================================================

async def example_error_handling():
    """Example: Error handling."""
    print("\n" + "="*60)
    print("EXAMPLE 10: Error Handling")
    print("="*60)
    
    runtime = HelixRuntime()
    await runtime.initialize()
    
    try:
        # Try to execute with invalid input
        result = await runtime.llm_bridge.generate(None)
    except TypeError as e:
        print(f"\nCaught TypeError: {e}")
    except Exception as e:
        print(f"\nCaught Exception: {e}")
    
    try:
        # Try to execute non-existent tool
        result = await runtime.tool_executor.execute("non_existent_tool")
    except Exception as e:
        print(f"Caught Exception: {e}")
    
    print("\nError handling completed successfully")
    
    await runtime.shutdown()


# =============================================================================
# MAIN
# =============================================================================

async def main():
    """Run all examples."""
    print("\n" + "="*60)
    print("HELIX-CORE BASIC USAGE EXAMPLES")
    print("="*60)
    
    examples = [
        example_basic_generation,
        example_token_counting,
        example_streaming,
        example_tools,
        example_reasoning,
        example_self_consistency,
        example_batch_processing,
        example_ucf_metrics,
        example_context,
        example_error_handling,
    ]
    
    for example in examples:
        try:
            await example()
        except Exception as e:
            logger.error(f"Error in {example.__name__}: {e}")
    
    print("\n" + "="*60)
    print("ALL EXAMPLES COMPLETED")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
