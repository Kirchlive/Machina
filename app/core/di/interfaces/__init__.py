"""
Service Interfaces (Protocols) for Dependency Injection

These protocols define the contracts that services must implement,
enabling loose coupling and better testability.
"""

from typing import Protocol, Any, Dict, Optional, List
from abc import abstractmethod
import httpx
from redis.asyncio import Redis

class IEventStore(Protocol):
    """Interface for event logging and monitoring"""
    
    @abstractmethod
    async def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log an event with associated data"""
        ...
    
    @abstractmethod
    async def get_events(self, event_type: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve logged events"""
        ...

class IConfigurationProvider(Protocol):
    """Interface for configuration management"""
    
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key"""
        ...
    
    @abstractmethod
    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific model"""
        ...
    
    @abstractmethod
    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Get all model configurations"""
        ...

class IHTTPClientProvider(Protocol):
    """Interface for HTTP client management"""
    
    @abstractmethod
    async def get_client(self) -> httpx.AsyncClient:
        """Get HTTP client instance"""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close HTTP client connections"""
        ...

class IRedisProvider(Protocol):
    """Interface for Redis connection management"""
    
    @abstractmethod
    async def get_client(self) -> Redis:
        """Get Redis client instance"""
        ...
    
    @abstractmethod
    async def close(self) -> None:
        """Close Redis connection"""
        ...

class IAdapterFactory(Protocol):
    """Interface for creating LLM adapters"""
    
    @abstractmethod
    async def create_adapter(self, model_name: str, config: Dict[str, Any]) -> Any:
        """Create an adapter for the specified model"""
        ...
    
    @abstractmethod
    def get_available_adapters(self) -> List[str]:
        """Get list of available adapter types"""
        ...

class ICircuitBreakerFactory(Protocol):
    """Interface for creating circuit breakers"""
    
    @abstractmethod
    def create_circuit_breaker(self, 
                             failure_threshold: int = 5,
                             recovery_timeout: int = 60,
                             expected_exception: type = Exception) -> Any:
        """Create a circuit breaker instance"""
        ...

class IRouter(Protocol):
    """Interface for message routing"""
    
    @abstractmethod
    async def route_message(self, 
                          conversation_id: str,
                          target_llm_name: str,
                          prompt: str,
                          **kwargs) -> str:
        """Route a message to the appropriate LLM"""
        ...

class ILogger(Protocol):
    """Interface for logging"""
    
    @abstractmethod
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        ...
    
    @abstractmethod
    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        ...
    
    @abstractmethod
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        ...
    
    @abstractmethod
    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        ...

class IStateRepository(Protocol):
    """Interface for state persistence"""
    
    @abstractmethod
    async def save_state(self, key: str, state: Dict[str, Any]) -> None:
        """Save state data"""
        ...
    
    @abstractmethod
    async def load_state(self, key: str) -> Optional[Dict[str, Any]]:
        """Load state data"""
        ...
    
    @abstractmethod
    async def delete_state(self, key: str) -> None:
        """Delete state data"""
        ...

class ITelemetry(Protocol):
    """Interface for telemetry/observability (e.g., Langfuse)"""
    
    @abstractmethod
    async def trace_start(self, trace_name: str, metadata: Dict[str, Any]) -> str:
        """Start a new trace and return trace ID"""
        ...
    
    @abstractmethod
    async def trace_end(self, trace_id: str, result: Any) -> None:
        """End a trace with result"""
        ...
    
    @abstractmethod
    async def log_metric(self, metric_name: str, value: float, tags: Dict[str, str]) -> None:
        """Log a metric with tags"""
        ...

# Export all interfaces
__all__ = [
    'IEventStore',
    'IConfigurationProvider', 
    'IHTTPClientProvider',
    'IRedisProvider',
    'IAdapterFactory',
    'ICircuitBreakerFactory',
    'IRouter',
    'ILogger',
    'IStateRepository',
    'ITelemetry'
]