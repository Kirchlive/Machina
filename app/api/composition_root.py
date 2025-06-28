# api_server/composition_root.py
"""
Composition Root for Dependency Injection

This module is responsible for wiring all dependencies together
and creating the object graph for the application.
"""

import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from app.core.di.container import ServiceContainer
from app.core.di.interfaces import *
from app.core.services import (
    HTTPClientService,
    EventStoreService,
    RedisProviderService,
    CircuitBreakerFactoryService,
    LoggerService,
    TelemetryService
)
# Use fixed versions
from app.core.services.configuration_fixed import ConfigurationService
from app.core.services.adapter_factory_fixed import AdapterFactoryService

# Import DI versions of main components
from app.core.core_di import LLMBridgeCore
from app.core.routing.router_di import Router
from app.core.orchestration.agent_orchestrator_di import AgentOrchestrator
from app.core.repositories.redis_agent_state_repository import RedisAgentStateRepository

async def configure_services(config_path: Optional[Path] = None) -> ServiceContainer:
    """
    Configure and wire all services for the application
    
    Args:
        config_path: Optional path to configuration file
        
    Returns:
        Configured service container with all dependencies registered
    """
    container = ServiceContainer()
    
    # 1. Register Configuration Service (Singleton)
    container.register_singleton(
        IConfigurationProvider,
        lambda: ConfigurationService(
            config_path=config_path or Path(__file__).parent.parent.parent / "registry.yaml"
        )
    )
    
    # 2. Register Logger Service (Singleton)
    container.register_singleton(
        ILogger,
        lambda: LoggerService(
            name="llm_bridge",
            level=os.getenv("LOG_LEVEL", "INFO"),
            json_format=os.getenv("LOG_FORMAT", "").lower() == "json"
        )
    )
    
    # 3. Register HTTP Client Service (Singleton)
    container.register_singleton(
        IHTTPClientProvider,
        lambda: HTTPClientService(
            timeout=int(os.getenv("HTTP_TIMEOUT", "30")),
            verify_ssl=os.getenv("VERIFY_SSL", "true").lower() == "true"
        )
    )
    
    # 4. Register Redis Provider Service (Singleton)
    def create_redis_provider():
        config = container.resolve_sync(IConfigurationProvider)
        redis_config = config.get_redis_config()
        return RedisProviderService(**redis_config)
    
    container.register_singleton(
        IRedisProvider,
        create_redis_provider
    )
    
    # 5. Register Event Store Service (Singleton)
    container.register_singleton(
        IEventStore,
        lambda: EventStoreService(
            max_events=int(os.getenv("MAX_EVENTS", "10000")),
            persist_to_file=os.getenv("EVENT_LOG_FILE")
        )
    )
    
    # 6. Register Telemetry Service (Singleton)
    def create_telemetry():
        # Check if Langfuse is configured
        langfuse_client = None
        if all(os.getenv(key) for key in ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_HOST"]):
            try:
                from langfuse import Langfuse
                langfuse_client = Langfuse(
                    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
                    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
                    host=os.getenv("LANGFUSE_HOST")
                )
            except Exception as e:
                logger = container.resolve_sync(ILogger)
                logger.warning(f"Failed to initialize Langfuse: {e}")
        
        return TelemetryService(
            langfuse_client=langfuse_client,
            enable_metrics=os.getenv("ENABLE_METRICS", "true").lower() == "true"
        )
    
    container.register_singleton(
        ITelemetry,
        create_telemetry
    )
    
    # 7. Register Adapter Factory Service (Singleton)
    async def create_adapter_factory():
        http_provider = await container.resolve(IHTTPClientProvider)
        config_provider = await container.resolve(IConfigurationProvider)
        return AdapterFactoryService(
            http_client_provider=http_provider,
            config_provider=config_provider,
            plugin_directory=Path(__file__).parent.parent / "core" / "plugins"
        )
    
    container.register_singleton(
        IAdapterFactory,
        create_adapter_factory
    )
    
    # 8. Register Circuit Breaker Factory Service (Singleton)
    container.register_singleton(
        ICircuitBreakerFactory,
        lambda: CircuitBreakerFactoryService(
            default_failure_threshold=int(os.getenv("CIRCUIT_BREAKER_THRESHOLD", "5")),
            default_recovery_timeout=int(os.getenv("CIRCUIT_BREAKER_TIMEOUT", "60"))
        )
    )
    
    # 9. Register State Repository (Singleton)
    async def create_state_repository():
        logger = container.resolve_sync(ILogger)
        
        # Try Redis first
        try:
            redis_provider = await container.resolve(IRedisProvider)
            redis_client = await redis_provider.get_client()
            logger.info("Using Redis for state repository")
            return RedisAgentStateRepository(redis_client)
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            logger.warning("Falling back to in-memory state repository (data will not persist!)")
            
            # Import here to avoid circular dependency
            from app.core.repositories.memory_state_repository import InMemoryAgentStateRepository
            return InMemoryAgentStateRepository()
    
    container.register_singleton(
        IStateRepository,
        create_state_repository
    )
    
    # 10. Create and register Router (Singleton)
    async def create_router():
        config_provider = await container.resolve(IConfigurationProvider)
        adapter_factory = await container.resolve(IAdapterFactory)
        circuit_breaker_factory = await container.resolve(ICircuitBreakerFactory)
        event_store = await container.resolve(IEventStore)
        telemetry = await container.resolve(ITelemetry)
        logger = await container.resolve(ILogger)
        
        # Try to get Redis provider, but don't fail if unavailable
        redis_provider = None
        try:
            redis_provider = await container.resolve(IRedisProvider)
        except Exception as e:
            logger.warning(f"Redis not available for Router caching: {e}")
        
        # Load model configurations
        models = config_provider.get_all_models()
        
        # Create adapters for all models
        adapters = {}
        circuit_breakers = {}
        
        for model_name, model_config in models.items():
            if model_name.startswith('_'):
                continue
                
            try:
                # Create adapter
                adapter = await adapter_factory.create_adapter(model_name, model_config)
                adapters[model_name] = adapter
                
                # Create circuit breaker
                breaker_config = model_config.get('circuit_breaker', {})
                circuit_breaker = circuit_breaker_factory.create_from_config(breaker_config)
                circuit_breakers[model_name] = circuit_breaker
                
                logger.info(f"Created adapter and circuit breaker for model: {model_name}")
                
            except Exception as e:
                logger.error(f"Failed to create adapter for {model_name}: {e}")
        
        # Create router with all dependencies
        return Router(
            adapters=adapters,
            circuit_breakers=circuit_breakers,
            model_config=models,
            event_store=event_store,
            telemetry=telemetry,
            redis_provider=redis_provider,
            logger=logger
        )
    
    container.register_singleton(IRouter, create_router)
    
    # 11. Register LLMBridgeCore (Singleton)
    async def create_bridge():
        router = await container.resolve(IRouter)
        config_provider = await container.resolve(IConfigurationProvider)
        event_store = await container.resolve(IEventStore)
        telemetry = await container.resolve(ITelemetry)
        logger = await container.resolve(ILogger)
        
        bridge = LLMBridgeCore(
            router=router,
            config_provider=config_provider,
            event_store=event_store,
            telemetry=telemetry,
            logger=logger
        )
        
        # Initialize the bridge
        await bridge.initialize()
        
        return bridge
    
    container.register_singleton(LLMBridgeCore, create_bridge)
    
    # 12. Register AgentOrchestrator (Singleton)
    async def create_orchestrator():
        bridge = await container.resolve(LLMBridgeCore)
        state_repository = await container.resolve(IStateRepository)
        event_store = await container.resolve(IEventStore)
        telemetry = await container.resolve(ITelemetry)
        config_provider = await container.resolve(IConfigurationProvider)
        logger = await container.resolve(ILogger)
        
        return AgentOrchestrator(
            bridge=bridge,
            state_repository=state_repository,
            event_store=event_store,
            telemetry=telemetry,
            config_provider=config_provider,
            logger=logger
        )
    
    container.register_singleton(AgentOrchestrator, create_orchestrator)
    
    return container

async def initialize_application(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """
    Initialize the complete application
    
    Args:
        config_path: Optional configuration file path
        
    Returns:
        Dictionary with main application components
    """
    # Configure services
    container = await configure_services(config_path)
    
    # Resolve main components
    bridge = await container.resolve(LLMBridgeCore)
    orchestrator = await container.resolve(AgentOrchestrator)
    state_repository = await container.resolve(IStateRepository)
    
    return {
        'container': container,
        'bridge': bridge,
        'orchestrator': orchestrator,
        'state_repository': state_repository
    }

# Cleanup function for graceful shutdown
async def cleanup_services(container: ServiceContainer) -> None:
    """
    Cleanup all services during shutdown
    
    Args:
        container: Service container to dispose
    """
    logger = logging.getLogger(__name__)
    logger.info("Starting service cleanup...")
    
    try:
        await container.dispose()
        logger.info("Service cleanup completed")
    except Exception as e:
        logger.error(f"Error during service cleanup: {e}")