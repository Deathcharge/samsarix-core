"""
Advanced Features for Helix-Core

Caching, monitoring, optimization, and resilience patterns.
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar

T = TypeVar("T")


# =============================================================================
# CACHING SYSTEM
# =============================================================================

@dataclass
class CacheEntry:
    """Cache entry with metadata."""

    value: Any
    timestamp: float = field(default_factory=time.time)
    ttl: Optional[float] = None
    hits: int = 0
    size: int = 0

    @property
    def is_expired(self) -> bool:
        """Check if entry is expired."""
        if self.ttl is None:
            return False
        return time.time() - self.timestamp > self.ttl


class Cache:
    """Intelligent caching system."""

    def __init__(
        self,
        max_size: int = 1000,
        eviction_policy: str = "lru",
        default_ttl: Optional[float] = None,
    ):
        """Initialize cache.
        
        Args:
            max_size: Maximum cache size
            eviction_policy: Eviction policy (lru, lfu, fifo)
            default_ttl: Default time-to-live in seconds
        """
        self.max_size = max_size
        self.eviction_policy = eviction_policy
        self.default_ttl = default_ttl
        self.cache: Dict[str, CacheEntry] = OrderedDict()
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0,
        }

    def get(self, key: str) -> Optional[Any]:
        """Get value from cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None
        """
        if key not in self.cache:
            self.stats["misses"] += 1
            return None

        entry = self.cache[key]
        if entry.is_expired:
            del self.cache[key]
            self.stats["expirations"] += 1
            return None

        entry.hits += 1
        self.stats["hits"] += 1
        # Move to end for LRU
        self.cache.move_to_end(key)
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[float] = None,
    ) -> None:
        """Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
        """
        ttl = ttl or self.default_ttl
        entry = CacheEntry(value=value, ttl=ttl, size=len(str(value)))

        if key in self.cache:
            self.cache[key] = entry
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self._evict()
            self.cache[key] = entry

    def _evict(self) -> None:
        """Evict entry based on policy."""
        if self.eviction_policy == "lru":
            # Remove oldest (first) item
            self.cache.popitem(last=False)
        elif self.eviction_policy == "lfu":
            # Remove least frequently used
            min_key = min(self.cache, key=lambda k: self.cache[k].hits)
            del self.cache[min_key]
        elif self.eviction_policy == "fifo":
            # Remove first inserted
            self.cache.popitem(last=False)

        self.stats["evictions"] += 1

    def clear(self) -> None:
        """Clear cache."""
        self.cache.clear()
        self.stats = {"hits": 0, "misses": 0, "evictions": 0, "expirations": 0}

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.stats["hits"] + self.stats["misses"]
        hit_rate = (
            self.stats["hits"] / total if total > 0 else 0
        )
        return {
            **self.stats,
            "size": len(self.cache),
            "hit_rate": hit_rate,
            "total_requests": total,
        }


# =============================================================================
# MONITORING SYSTEM
# =============================================================================

@dataclass
class Metric:
    """Performance metric."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    unit: str = "ms"


class Monitor:
    """Performance monitoring system."""

    def __init__(self):
        """Initialize monitor."""
        self.metrics: List[Metric] = []
        self.active_timers: Dict[str, float] = {}

    def record_metric(
        self,
        name: str,
        value: float,
        unit: str = "ms",
    ) -> None:
        """Record a metric.
        
        Args:
            name: Metric name
            value: Metric value
            unit: Unit of measurement
        """
        metric = Metric(name=name, value=value, unit=unit)
        self.metrics.append(metric)

    def start_timer(self, name: str) -> None:
        """Start a timer.
        
        Args:
            name: Timer name
        """
        self.active_timers[name] = time.time()

    def stop_timer(self, name: str) -> float:
        """Stop a timer and record metric.
        
        Args:
            name: Timer name
            
        Returns:
            Elapsed time in milliseconds
        """
        if name not in self.active_timers:
            return 0

        elapsed = (time.time() - self.active_timers[name]) * 1000
        del self.active_timers[name]
        self.record_metric(name, elapsed)
        return elapsed

    def get_metrics(self, name: Optional[str] = None) -> List[Metric]:
        """Get metrics.
        
        Args:
            name: Filter by metric name
            
        Returns:
            List of metrics
        """
        if name:
            return [m for m in self.metrics if m.name == name]
        return self.metrics

    def get_statistics(self, name: str) -> Dict[str, float]:
        """Get statistics for a metric.
        
        Args:
            name: Metric name
            
        Returns:
            Statistics dictionary
        """
        values = [m.value for m in self.get_metrics(name)]
        if not values:
            return {}

        return {
            "count": len(values),
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "total": sum(values),
        }


# =============================================================================
# RESILIENCE PATTERNS
# =============================================================================

class RetryPolicy:
    """Retry policy with exponential backoff."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0,
    ):
        """Initialize retry policy.
        
        Args:
            max_attempts: Maximum retry attempts
            initial_delay: Initial delay in seconds
            max_delay: Maximum delay in seconds
            backoff_factor: Backoff multiplication factor
        """
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor

    def get_delay(self, attempt: int) -> float:
        """Get delay for attempt.
        
        Args:
            attempt: Attempt number (1-based)
            
        Returns:
            Delay in seconds
        """
        delay = self.initial_delay * (self.backoff_factor ** (attempt - 1))
        return min(delay, self.max_delay)

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs,
    ) -> Any:
        """Execute function with retry.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If all attempts fail
        """
        last_error = None

        for attempt in range(1, self.max_attempts + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_attempts:
                    delay = self.get_delay(attempt)
                    await asyncio.sleep(delay)

        raise last_error


class CircuitBreaker:
    """Circuit breaker pattern."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Failures before opening
            recovery_timeout: Timeout before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half_open

    def record_success(self) -> None:
        """Record successful call."""
        self.failure_count = 0
        self.state = "closed"

    def record_failure(self) -> None:
        """Record failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = "open"

    def can_execute(self) -> bool:
        """Check if call can be executed.
        
        Returns:
            True if call can be executed
        """
        if self.state == "closed":
            return True

        if self.state == "open":
            if (
                time.time() - self.last_failure_time
                > self.recovery_timeout
            ):
                self.state = "half_open"
                return True
            return False

        return True  # half_open


class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(
        self,
        rate: float,
        burst: int = 1,
    ):
        """Initialize rate limiter.
        
        Args:
            rate: Requests per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_update = time.time()

    async def acquire(self, tokens: int = 1) -> None:
        """Acquire tokens.
        
        Args:
            tokens: Number of tokens to acquire
        """
        while self.tokens < tokens:
            now = time.time()
            elapsed = now - self.last_update
            self.tokens = min(
                self.burst,
                self.tokens + elapsed * self.rate,
            )
            self.last_update = now

            if self.tokens < tokens:
                await asyncio.sleep(0.01)

        self.tokens -= tokens


# =============================================================================
# PERFORMANCE OPTIMIZATION
# =============================================================================

class PerformanceOptimizer:
    """Performance optimization utilities."""

    @staticmethod
    def batch_items(items: List[T], batch_size: int) -> List[List[T]]:
        """Batch items for processing.
        
        Args:
            items: Items to batch
            batch_size: Batch size
            
        Returns:
            List of batches
        """
        return [
            items[i : i + batch_size]
            for i in range(0, len(items), batch_size)
        ]

    @staticmethod
    async def parallel_execute(
        tasks: List[Callable],
        max_concurrent: int = 10,
    ) -> List[Any]:
        """Execute tasks in parallel with concurrency limit.
        
        Args:
            tasks: List of async tasks
            max_concurrent: Maximum concurrent tasks
            
        Returns:
            List of results
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def execute_with_limit(task):
            async with semaphore:
                return await task

        return await asyncio.gather(*[execute_with_limit(t) for t in tasks])


# =============================================================================
# HEALTH CHECK SYSTEM
# =============================================================================

@dataclass
class HealthStatus:
    """Health status information."""

    status: str  # healthy, degraded, unhealthy
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)


class HealthChecker:
    """System health checking."""

    def __init__(self):
        """Initialize health checker."""
        self.checks: Dict[str, Callable] = {}
        self.last_status: Optional[HealthStatus] = None

    def register_check(self, name: str, check_func: Callable) -> None:
        """Register a health check.
        
        Args:
            name: Check name
            check_func: Async check function
        """
        self.checks[name] = check_func

    async def check_health(self) -> HealthStatus:
        """Check system health.
        
        Returns:
            Health status
        """
        details = {}
        unhealthy = False

        for name, check_func in self.checks.items():
            try:
                result = await check_func()
                details[name] = {"status": "ok", "result": result}
            except Exception as e:
                details[name] = {"status": "error", "error": str(e)}
                unhealthy = True

        status = "unhealthy" if unhealthy else "healthy"
        self.last_status = HealthStatus(status=status, details=details)
        return self.last_status
