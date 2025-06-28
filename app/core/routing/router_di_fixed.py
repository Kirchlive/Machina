# llm_bridge/routing/router_di.py
"""
Refactored Router with Dependency Injection

This version uses injected dependencies instead of creating them internally.
"""

from typing import Dict, Optional, Any
import hashlib
import json
import logging
from ..di.interfaces import (
    IRouter,
    IEventStore,
    ITelemetry,
    IRedisProvider,
    ILogger
)
from ..orchestration.conversation_state import ConversationStateMachine
from ..orchestration.circuit_breaker import CircuitBreakerError

class Router(IRouter):
    """
    Message router with dependency injection
    
    Routes messages to appropriate LLM adapters through circuit breakers,
    with caching and conversation state management.
    """
    
    def __init__(self,
                 adapters: Dict[str, Any],
                 circuit_breakers: Dict[str, Any],
                 model_config: Dict[str, Any],
                 event_store: IEventStore,
                 telemetry: ITelemetry,
                 redis_provider: Optional[IRedisProvider] = None,
                 logger: Optional[ILogger] = None):
        """
        Initialize router with injected dependencies
        
        Args:
            adapters: Dictionary of LLM adapters
            circuit_breakers: Dictionary of circuit breakers
            model_config: Model configuration
            event_store: Event logging service
            telemetry: Telemetry service
            redis_provider: Optional Redis provider for caching
            logger: Optional logger
        """
        self.adapters = adapters
        self.circuit_breakers = circuit_breakers
        self.model_config = model_config
        self.event_store = event_store
        self.telemetry = telemetry
        self.redis_provider = redis_provider
        self.logger = logger or logging.getLogger(__name__)
        
        # Conversation state management
        self.active_conversations: Dict[str, ConversationStateMachine] = {}
        
        # Cache client will be initialized lazily
        self._cache_client = None
        self._cache_enabled = redis_provider is not None
        
        self.logger.info(
            f"Router initialized with {len(adapters)} adapters, "
            f"cache {'enabled' if self._cache_enabled else 'disabled'}"
        )
    
    async def _get_cache_client(self):
        """Get Redis cache client (lazy initialization)"""
        if not self._cache_enabled:
            return None
            
        if self._cache_client is None:
            try:
                self._cache_client = await self.redis_provider.get_client()
                await self._cache_client.ping()
                self.logger.debug("Redis cache client initialized")
            except Exception as e:
                self.logger.warning(f"Failed to initialize cache client: {e}")
                self._cache_enabled = False
                return None
                
        return self._cache_client
    
    def _generate_cache_key(self, target_llm: str, prompt: str, kwargs: Dict) -> str:
        """Generate cache key for LLM response"""
        cache_data = f"{target_llm}:{prompt}:{json.dumps(kwargs, sort_keys=True)}"
        return f"llm_response:{hashlib.sha256(cache_data.encode()).hexdigest()}"
    
    async def _check_cache(self, cache_key: str) -> Optional[str]:
        """Check cache for existing response"""
        cache = await self._get_cache_client()
        if not cache:
            return None
            
        try:
            cached = await cache.get(cache_key)
            if cached:
                self.logger.debug(f"Cache hit: {cache_key[:20]}...")
                return json.loads(cached)
        except Exception as e:
            self.logger.warning(f"Cache read error: {e}")
            
        return None
    
    async def _update_cache(self, cache_key: str, response: str, ttl: int = 3600) -> None:
        """Update cache with new response"""
        cache = await self._get_cache_client()
        if not cache:
            return
            
        try:
            await cache.set(cache_key, json.dumps(response), ex=ttl)
            self.logger.debug(f"Cache updated: {cache_key[:20]}...")
        except Exception as e:
            self.logger.warning(f"Cache write error: {e}")
    
    async def route_message(self,
                          conversation_id: str,
                          target_llm_name: str,
                          prompt: str,
                          **kwargs) -> str:
        """
        Route a message to the appropriate LLM
        
        Args:
            conversation_id: Unique conversation identifier
            target_llm_name: Name of the target LLM
            prompt: Message prompt
            **kwargs: Additional routing parameters
            
        Returns:
            Response from the LLM
        """
        # Start telemetry trace
        trace_id = await self.telemetry.trace_start(
            "route_message",
            {
                "conversation_id": conversation_id,
                "target_llm": target_llm_name,
                "prompt_length": len(prompt)
            }
        )
        
        try:
            # Check cache first
            cache_key = self._generate_cache_key(target_llm_name, prompt, kwargs)
            cached_response = await self._check_cache(cache_key)
            if cached_response:
                await self.telemetry.trace_end(trace_id, {"cache_hit": True})
                return cached_response
            
            # Log routing event
            await self.event_store.log_event(
                "routing_start",
                {
                    "conversation_id": conversation_id,
                    "target_llm": target_llm_name
                }
            )
            
            # Get or create conversation state
            if conversation_id not in self.active_conversations:
                self.active_conversations[conversation_id] = ConversationStateMachine(conversation_id)
            state_machine = self.active_conversations[conversation_id]
            
            # Determine actual LLM to use based on configuration
            actual_llm = self._determine_actual_llm(target_llm_name)
            
            # Get adapter and circuit breaker
            adapter = self.adapters.get(actual_llm)
            circuit_breaker = self.circuit_breakers.get(actual_llm)
            
            if not adapter:
                raise ValueError(f"No adapter found for LLM: {actual_llm}")
            if not circuit_breaker:
                raise ValueError(f"No circuit breaker found for LLM: {actual_llm}")
            
            # Call through circuit breaker
            try:
                response = await circuit_breaker.execute(
                    adapter.complete,
                    prompt=prompt,
                    conversation_id=conversation_id,
                    **kwargs
                )
                
                # Update conversation state
                state_machine.record_response(prompt, response, actual_llm)
                
                # Update cache
                await self._update_cache(cache_key, response)
                
                # Log success
                await self.event_store.log_event(
                    "routing_success",
                    {
                        "conversation_id": conversation_id,
                        "actual_llm": actual_llm,
                        "response_length": len(response)
                    }
                )
                
                # End trace
                await self.telemetry.trace_end(
                    trace_id,
                    {
                        "actual_llm": actual_llm,
                        "cache_hit": False,
                        "response_length": len(response)
                    }
                )
                
                return response
                
            except CircuitBreakerError as e:
                # Circuit breaker is open
                await self.event_store.log_event(
                    "circuit_breaker_open",
                    {
                        "conversation_id": conversation_id,
                        "llm": actual_llm,
                        "error": str(e)
                    }
                )
                raise
                
        except Exception as e:
            # Log error
            await self.event_store.log_event(
                "routing_error",
                {
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )
            
            # End trace with error
            await self.telemetry.trace_end(trace_id, error=str(e))
            
            # Re-raise
            raise
    
    def _determine_actual_llm(self, target_llm_name: str) -> str:
        """
        Determine the actual LLM to use based on configuration
        
        This handles routing logic like using a specific service
        for multiple models (e.g., OpenRouter for various models).
        """
        # Check if this is a direct model
        if target_llm_name in self.adapters:
            return target_llm_name
        
        # Check model configuration for adapter service
        model_config = self.model_config.get(target_llm_name, {})
        adapter_service = model_config.get('adapter_service')
        
        if adapter_service and adapter_service in self.adapters:
            self.logger.debug(
                f"Routing {target_llm_name} through service: {adapter_service}"
            )
            return adapter_service
        
        # Default: return as-is and let it fail if not found
        return target_llm_name
    
    def get_conversation_state(self, conversation_id: str) -> Optional[ConversationStateMachine]:
        """Get conversation state for a specific conversation"""
        return self.active_conversations.get(conversation_id)
    
    def clear_conversation(self, conversation_id: str) -> None:
        """Clear conversation state"""
        if conversation_id in self.active_conversations:
            del self.active_conversations[conversation_id]
            self.logger.debug(f"Cleared conversation state: {conversation_id}")