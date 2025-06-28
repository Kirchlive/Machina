"""
Circuit Breaker Factory Service Implementation

Creates and configures circuit breaker instances for fault tolerance.
"""

from typing import Optional, Dict, Any
import logging
from app.core.di.interfaces import ICircuitBreakerFactory
from app.core.orchestration.circuit_breaker import CircuitBreaker

class CircuitBreakerFactoryService(ICircuitBreakerFactory):
    """
    Concrete implementation of ICircuitBreakerFactory
    
    Creates circuit breakers with:
    - Configurable failure thresholds
    - Recovery timeouts
    - Exception handling strategies
    """
    
    def __init__(self,
                 default_failure_threshold: int = 5,
                 default_recovery_timeout: int = 60,
                 default_expected_exception: type = Exception):
        """
        Initialize the circuit breaker factory
        
        Args:
            default_failure_threshold: Default consecutive failures before opening
            default_recovery_timeout: Default recovery timeout in seconds
            default_expected_exception: Default exception type to catch
        """
        self._default_failure_threshold = default_failure_threshold
        self._default_recovery_timeout = default_recovery_timeout
        self._default_expected_exception = default_expected_exception
        self._logger = logging.getLogger(__name__)
        
    def create_circuit_breaker(self,
                             failure_threshold: Optional[int] = None,
                             recovery_timeout: Optional[int] = None,
                             expected_exception: Optional[type] = None) -> CircuitBreaker:
        """
        Create a circuit breaker instance
        
        Args:
            failure_threshold: Consecutive failures before opening (uses default if None)
            recovery_timeout: Recovery timeout in seconds (uses default if None)
            expected_exception: Exception type to catch (uses default if None)
            
        Returns:
            Configured circuit breaker instance
        """
        # Use provided values or defaults
        threshold = failure_threshold or self._default_failure_threshold
        timeout = recovery_timeout or self._default_recovery_timeout
        exception = expected_exception or self._default_expected_exception
        
        # Create circuit breaker with correct parameter names
        circuit_breaker = CircuitBreaker(
            max_failures=threshold,
            reset_timeout=timeout,
            expected_exception=exception
        )
        
        self._logger.debug(
            f"Created circuit breaker: threshold={threshold}, "
            f"timeout={timeout}s, exception={exception.__name__}"
        )
        
        return circuit_breaker
    
    def create_from_config(self, config: Dict[str, Any]) -> CircuitBreaker:
        """
        Create circuit breaker from configuration dictionary
        
        Args:
            config: Configuration with keys:
                    - failure_threshold
                    - recovery_timeout
                    - expected_exception (as string)
                    
        Returns:
            Configured circuit breaker
        """
        failure_threshold = config.get('failure_threshold', self._default_failure_threshold)
        recovery_timeout = config.get('recovery_timeout', self._default_recovery_timeout)
        
        # Handle exception type from string
        exception_name = config.get('expected_exception', 'Exception')
        expected_exception = self._resolve_exception_type(exception_name)
        
        return self.create_circuit_breaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
            expected_exception=expected_exception
        )
    
    def _resolve_exception_type(self, exception_name: str) -> type:
        """
        Resolve exception type from string name
        
        Args:
            exception_name: Name of the exception class
            
        Returns:
            Exception class type
        """
        # Common exception mappings
        exception_map = {
            'Exception': Exception,
            'RuntimeError': RuntimeError,
            'ValueError': ValueError,
            'TypeError': TypeError,
            'ConnectionError': ConnectionError,
            'TimeoutError': TimeoutError,
            'HTTPError': Exception,  # Generic for now
            'RequestException': Exception,  # Generic for now
        }
        
        return exception_map.get(exception_name, Exception)

class AdaptiveCircuitBreakerFactory(CircuitBreakerFactoryService):
    """
    Circuit breaker factory with adaptive thresholds
    
    Adjusts circuit breaker parameters based on observed behavior.
    """
    
    def __init__(self, **kwargs):
        """Initialize with adaptive capabilities"""
        super().__init__(**kwargs)
        self._breaker_stats: Dict[str, Dict[str, Any]] = {}
    
    def create_adaptive_circuit_breaker(self,
                                      breaker_id: str,
                                      base_config: Optional[Dict[str, Any]] = None) -> CircuitBreaker:
        """
        Create an adaptive circuit breaker
        
        Args:
            breaker_id: Unique identifier for tracking
            base_config: Base configuration
            
        Returns:
            Circuit breaker with adaptive parameters
        """
        # Get historical stats if available
        stats = self._breaker_stats.get(breaker_id, {})
        
        # Adjust parameters based on history
        if stats:
            # Example adaptive logic
            avg_failure_rate = stats.get('avg_failure_rate', 0)
            if avg_failure_rate > 0.5:
                # High failure rate - be more conservative
                failure_threshold = 3
                recovery_timeout = 120
            elif avg_failure_rate < 0.1:
                # Low failure rate - be more lenient
                failure_threshold = 10
                recovery_timeout = 30
            else:
                # Normal parameters
                failure_threshold = self._default_failure_threshold
                recovery_timeout = self._default_recovery_timeout
        else:
            # No history - use defaults
            failure_threshold = self._default_failure_threshold
            recovery_timeout = self._default_recovery_timeout
        
        # Override with base config if provided
        if base_config:
            failure_threshold = base_config.get('failure_threshold', failure_threshold)
            recovery_timeout = base_config.get('recovery_timeout', recovery_timeout)
        
        # Create breaker
        breaker = self.create_circuit_breaker(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout
        )
        
        # Initialize stats tracking
        self._breaker_stats[breaker_id] = {
            'total_calls': 0,
            'failures': 0,
            'avg_failure_rate': 0
        }
        
        self._logger.info(
            f"Created adaptive circuit breaker '{breaker_id}': "
            f"threshold={failure_threshold}, timeout={recovery_timeout}s"
        )
        
        return breaker
    
    def update_stats(self, breaker_id: str, success: bool) -> None:
        """
        Update statistics for adaptive adjustment
        
        Args:
            breaker_id: Breaker identifier
            success: Whether the call succeeded
        """
        if breaker_id in self._breaker_stats:
            stats = self._breaker_stats[breaker_id]
            stats['total_calls'] += 1
            if not success:
                stats['failures'] += 1
            
            # Update average failure rate
            stats['avg_failure_rate'] = stats['failures'] / stats['total_calls']