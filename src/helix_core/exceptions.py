"""
Custom Exceptions for Helix-Core

Comprehensive exception hierarchy for error handling and recovery.
"""

from typing import Any, Dict, Optional


# =============================================================================
# BASE EXCEPTIONS
# =============================================================================

class HelixCoreException(Exception):
    """Base exception for all Helix-Core errors."""

    def __init__(
        self,
        message: str,
        error_code: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """Initialize exception.
        
        Args:
            message: Error message
            error_code: Error code for categorization
            context: Additional context information
        """
        self.message = message
        self.error_code = error_code or "HELIX_ERROR"
        self.context = context or {}
        super().__init__(self.message)

    def __str__(self) -> str:
        """String representation."""
        if self.context:
            context_str = ", ".join(f"{k}={v}" for k, v in self.context.items())
            return f"[{self.error_code}] {self.message} ({context_str})"
        return f"[{self.error_code}] {self.message}"


# =============================================================================
# LLM PROVIDER EXCEPTIONS
# =============================================================================

class LLMProviderError(HelixCoreException):
    """Error from LLM provider."""

    def __init__(self, message: str, provider: Optional[str] = None, **kwargs):
        """Initialize LLM provider error.
        
        Args:
            message: Error message
            provider: Provider name
            **kwargs: Additional context
        """
        context = {"provider": provider} if provider else {}
        context.update(kwargs)
        super().__init__(message, "LLM_PROVIDER_ERROR", context)


class LLMProviderNotFound(LLMProviderError):
    """LLM provider not found."""

    def __init__(self, provider_name: str):
        """Initialize.
        
        Args:
            provider_name: Name of provider not found
        """
        super().__init__(
            f"LLM provider '{provider_name}' not found",
            provider=provider_name,
            error_code="LLM_PROVIDER_NOT_FOUND",
        )


class LLMProviderUnavailable(LLMProviderError):
    """LLM provider is unavailable."""

    def __init__(self, provider: str, reason: Optional[str] = None):
        """Initialize.
        
        Args:
            provider: Provider name
            reason: Reason for unavailability
        """
        message = f"LLM provider '{provider}' is unavailable"
        if reason:
            message += f": {reason}"
        super().__init__(message, provider=provider, reason=reason)


class APIKeyError(LLMProviderError):
    """API key error."""

    def __init__(self, provider: str, message: str = "Invalid or missing API key"):
        """Initialize.
        
        Args:
            provider: Provider name
            message: Error message
        """
        super().__init__(message, provider=provider, error_code="API_KEY_ERROR")


class RateLimitError(LLMProviderError):
    """Rate limit exceeded."""

    def __init__(
        self,
        provider: str,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        """Initialize.
        
        Args:
            provider: Provider name
            retry_after: Seconds to wait before retry
            **kwargs: Additional context
        """
        message = f"Rate limit exceeded for provider '{provider}'"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        context = {"retry_after": retry_after}
        context.update(kwargs)
        super().__init__(message, provider=provider, error_code="RATE_LIMIT_ERROR")
        self.retry_after = retry_after


class TokenLimitError(LLMProviderError):
    """Token limit exceeded."""

    def __init__(
        self,
        provider: str,
        tokens: int,
        limit: int,
        **kwargs
    ):
        """Initialize.
        
        Args:
            provider: Provider name
            tokens: Number of tokens
            limit: Token limit
            **kwargs: Additional context
        """
        message = f"Token limit exceeded: {tokens} > {limit}"
        super().__init__(
            message,
            provider=provider,
            error_code="TOKEN_LIMIT_ERROR",
            tokens=tokens,
            limit=limit,
        )
        self.tokens = tokens
        self.limit = limit


class ModelNotSupportedError(LLMProviderError):
    """Model not supported by provider."""

    def __init__(self, provider: str, model: str):
        """Initialize.
        
        Args:
            provider: Provider name
            model: Model name
        """
        super().__init__(
            f"Model '{model}' is not supported by provider '{provider}'",
            provider=provider,
            model=model,
            error_code="MODEL_NOT_SUPPORTED_ERROR",
        )


# =============================================================================
# TOOL EXCEPTIONS
# =============================================================================

class ToolError(HelixCoreException):
    """Base tool error."""

    def __init__(self, message: str, tool_name: Optional[str] = None, **kwargs):
        """Initialize tool error.
        
        Args:
            message: Error message
            tool_name: Name of tool
            **kwargs: Additional context
        """
        context = {"tool": tool_name} if tool_name else {}
        context.update(kwargs)
        super().__init__(message, "TOOL_ERROR", context)


class ToolNotFoundError(ToolError):
    """Tool not found."""

    def __init__(self, tool_name: str):
        """Initialize.
        
        Args:
            tool_name: Name of tool not found
        """
        super().__init__(
            f"Tool '{tool_name}' not found",
            tool_name=tool_name,
            error_code="TOOL_NOT_FOUND_ERROR",
        )


class ToolExecutionError(ToolError):
    """Error executing tool."""

    def __init__(
        self,
        tool_name: str,
        message: str,
        original_error: Optional[Exception] = None,
        **kwargs
    ):
        """Initialize.
        
        Args:
            tool_name: Name of tool
            message: Error message
            original_error: Original exception
            **kwargs: Additional context
        """
        super().__init__(
            message,
            tool_name=tool_name,
            error_code="TOOL_EXECUTION_ERROR",
            original_error=str(original_error) if original_error else None,
        )
        self.original_error = original_error


class ToolTimeoutError(ToolError):
    """Tool execution timeout."""

    def __init__(self, tool_name: str, timeout: float):
        """Initialize.
        
        Args:
            tool_name: Name of tool
            timeout: Timeout in seconds
        """
        super().__init__(
            f"Tool '{tool_name}' execution timed out after {timeout} seconds",
            tool_name=tool_name,
            timeout=timeout,
            error_code="TOOL_TIMEOUT_ERROR",
        )


class ToolValidationError(ToolError):
    """Tool validation error."""

    def __init__(self, tool_name: str, message: str, **kwargs):
        """Initialize.
        
        Args:
            tool_name: Name of tool
            message: Error message
            **kwargs: Additional context
        """
        super().__init__(
            message,
            tool_name=tool_name,
            error_code="TOOL_VALIDATION_ERROR",
        )


# =============================================================================
# REASONING EXCEPTIONS
# =============================================================================

class ReasoningError(HelixCoreException):
    """Base reasoning error."""

    def __init__(self, message: str, method: Optional[str] = None, **kwargs):
        """Initialize reasoning error.
        
        Args:
            message: Error message
            method: Reasoning method
            **kwargs: Additional context
        """
        context = {"method": method} if method else {}
        context.update(kwargs)
        super().__init__(message, "REASONING_ERROR", context)


class ReasoningTimeoutError(ReasoningError):
    """Reasoning timeout."""

    def __init__(self, method: str, timeout: float):
        """Initialize.
        
        Args:
            method: Reasoning method
            timeout: Timeout in seconds
        """
        super().__init__(
            f"Reasoning with method '{method}' timed out after {timeout} seconds",
            method=method,
            timeout=timeout,
            error_code="REASONING_TIMEOUT_ERROR",
        )


class ReasoningMaxStepsExceeded(ReasoningError):
    """Maximum reasoning steps exceeded."""

    def __init__(self, method: str, max_steps: int, steps_taken: int):
        """Initialize.
        
        Args:
            method: Reasoning method
            max_steps: Maximum steps allowed
            steps_taken: Steps actually taken
        """
        super().__init__(
            f"Reasoning exceeded maximum steps: {steps_taken} > {max_steps}",
            method=method,
            max_steps=max_steps,
            steps_taken=steps_taken,
            error_code="REASONING_MAX_STEPS_EXCEEDED_ERROR",
        )


# =============================================================================
# VALIDATION EXCEPTIONS
# =============================================================================

class ValidationError(HelixCoreException):
    """Validation error."""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        """Initialize validation error.
        
        Args:
            message: Error message
            field: Field that failed validation
            **kwargs: Additional context
        """
        context = {"field": field} if field else {}
        context.update(kwargs)
        super().__init__(message, "VALIDATION_ERROR", context)


class SchemaValidationError(ValidationError):
    """Schema validation error."""

    def __init__(self, message: str, schema: Optional[Dict] = None, **kwargs):
        """Initialize.
        
        Args:
            message: Error message
            schema: Schema that failed validation
            **kwargs: Additional context
        """
        super().__init__(
            message,
            error_code="SCHEMA_VALIDATION_ERROR",
            schema=str(schema) if schema else None,
        )


class TypeValidationError(ValidationError):
    """Type validation error."""

    def __init__(self, field: str, expected_type: str, actual_type: str):
        """Initialize.
        
        Args:
            field: Field name
            expected_type: Expected type
            actual_type: Actual type
        """
        super().__init__(
            f"Type mismatch for field '{field}': expected {expected_type}, got {actual_type}",
            field=field,
            expected_type=expected_type,
            actual_type=actual_type,
            error_code="TYPE_VALIDATION_ERROR",
        )


# =============================================================================
# CONTEXT EXCEPTIONS
# =============================================================================

class ContextError(HelixCoreException):
    """Context error."""

    def __init__(self, message: str, **kwargs):
        """Initialize context error.
        
        Args:
            message: Error message
            **kwargs: Additional context
        """
        super().__init__(message, "CONTEXT_ERROR", kwargs)


class ContextNotInitializedError(ContextError):
    """Context not initialized."""

    def __init__(self):
        """Initialize."""
        super().__init__(
            "Context not initialized",
            error_code="CONTEXT_NOT_INITIALIZED_ERROR",
        )


class ContextKeyError(ContextError):
    """Context key error."""

    def __init__(self, key: str):
        """Initialize.
        
        Args:
            key: Key not found
        """
        super().__init__(
            f"Key '{key}' not found in context",
            key=key,
            error_code="CONTEXT_KEY_ERROR",
        )


# =============================================================================
# RUNTIME EXCEPTIONS
# =============================================================================

class RuntimeError(HelixCoreException):
    """Runtime error."""

    def __init__(self, message: str, **kwargs):
        """Initialize runtime error.
        
        Args:
            message: Error message
            **kwargs: Additional context
        """
        super().__init__(message, "RUNTIME_ERROR", kwargs)


class RuntimeNotInitializedError(RuntimeError):
    """Runtime not initialized."""

    def __init__(self):
        """Initialize."""
        super().__init__(
            "Runtime not initialized",
            error_code="RUNTIME_NOT_INITIALIZED_ERROR",
        )


class RuntimeShutdownError(RuntimeError):
    """Error during runtime shutdown."""

    def __init__(self, message: str):
        """Initialize.
        
        Args:
            message: Error message
        """
        super().__init__(
            message,
            error_code="RUNTIME_SHUTDOWN_ERROR",
        )


# =============================================================================
# CONFIGURATION EXCEPTIONS
# =============================================================================

class ConfigurationError(HelixCoreException):
    """Configuration error."""

    def __init__(self, message: str, config_key: Optional[str] = None, **kwargs):
        """Initialize configuration error.
        
        Args:
            message: Error message
            config_key: Configuration key
            **kwargs: Additional context
        """
        context = {"config_key": config_key} if config_key else {}
        context.update(kwargs)
        super().__init__(message, "CONFIGURATION_ERROR", context)


class MissingConfigurationError(ConfigurationError):
    """Missing required configuration."""

    def __init__(self, config_key: str):
        """Initialize.
        
        Args:
            config_key: Missing configuration key
        """
        super().__init__(
            f"Missing required configuration: {config_key}",
            config_key=config_key,
            error_code="MISSING_CONFIGURATION_ERROR",
        )


class InvalidConfigurationError(ConfigurationError):
    """Invalid configuration value."""

    def __init__(self, config_key: str, message: str):
        """Initialize.
        
        Args:
            config_key: Configuration key
            message: Error message
        """
        super().__init__(
            f"Invalid configuration for '{config_key}': {message}",
            config_key=config_key,
            error_code="INVALID_CONFIGURATION_ERROR",
        )


# =============================================================================
# ASYNC EXCEPTIONS
# =============================================================================

class AsyncError(HelixCoreException):
    """Async operation error."""

    def __init__(self, message: str, **kwargs):
        """Initialize async error.
        
        Args:
            message: Error message
            **kwargs: Additional context
        """
        super().__init__(message, "ASYNC_ERROR", kwargs)


class AsyncTimeoutError(AsyncError):
    """Async operation timeout."""

    def __init__(self, operation: str, timeout: float):
        """Initialize.
        
        Args:
            operation: Operation name
            timeout: Timeout in seconds
        """
        super().__init__(
            f"Async operation '{operation}' timed out after {timeout} seconds",
            operation=operation,
            timeout=timeout,
            error_code="ASYNC_TIMEOUT_ERROR",
        )


class AsyncCancelledError(AsyncError):
    """Async operation cancelled."""

    def __init__(self, operation: str):
        """Initialize.
        
        Args:
            operation: Operation name
        """
        super().__init__(
            f"Async operation '{operation}' was cancelled",
            operation=operation,
            error_code="ASYNC_CANCELLED_ERROR",
        )


# =============================================================================
# ERROR RECOVERY UTILITIES
# =============================================================================

class ErrorRecoveryStrategy:
    """Strategy for error recovery."""

    @staticmethod
    def is_retryable(error: Exception) -> bool:
        """Check if error is retryable.
        
        Args:
            error: Exception to check
            
        Returns:
            True if error is retryable
        """
        retryable_errors = (
            RateLimitError,
            AsyncTimeoutError,
            LLMProviderUnavailable,
        )
        return isinstance(error, retryable_errors)

    @staticmethod
    def get_retry_delay(error: Exception, attempt: int) -> float:
        """Get retry delay in seconds.
        
        Args:
            error: Exception
            attempt: Attempt number (1-based)
            
        Returns:
            Delay in seconds
        """
        if isinstance(error, RateLimitError) and error.retry_after:
            return float(error.retry_after)
        
        # Exponential backoff: 1, 2, 4, 8, 16 seconds
        return min(2 ** (attempt - 1), 60)

    @staticmethod
    def should_fallback(error: Exception) -> bool:
        """Check if fallback strategy should be used.
        
        Args:
            error: Exception
            
        Returns:
            True if fallback should be used
        """
        fallback_errors = (
            LLMProviderUnavailable,
            LLMProviderNotFound,
            ModelNotSupportedError,
        )
        return isinstance(error, fallback_errors)
