# llm_bridge/core_di.py
"""
Refactored LLMBridgeCore with Dependency Injection

This version uses constructor injection for all dependencies,
making the class more testable and loosely coupled.
"""

from typing import Dict, Optional, Any
import logging
from .di.interfaces import (
    IRouter, 
    IConfigurationProvider, 
    IEventStore, 
    ITelemetry,
    ILogger
)
from .config.schema import RegistrySchema

class LLMBridgeCore:
    """
    Core bridge class with dependency injection
    
    All dependencies are injected through the constructor,
    removing the need for factory methods and internal creation logic.
    """
    
    def __init__(self,
                 router: IRouter,
                 config_provider: IConfigurationProvider,
                 event_store: IEventStore,
                 telemetry: ITelemetry,
                 logger: Optional[ILogger] = None):
        """
        Initialize the bridge with injected dependencies
        
        Args:
            router: Message routing service
            config_provider: Configuration management service
            event_store: Event logging service
            telemetry: Telemetry/observability service
            logger: Optional logger (uses default if not provided)
        """
        self.router = router
        self.config_provider = config_provider
        self.event_store = event_store
        self.telemetry = telemetry
        self.logger = logger or logging.getLogger(__name__)
        
        # Cache for registry config if needed
        self._registry_config: Optional[RegistrySchema] = None
        
        self.logger.info("LLMBridgeCore initialized with dependency injection")
    
    async def initialize(self) -> None:
        """
        Initialize the bridge after construction
        
        This is where any async initialization logic goes,
        separated from the constructor.
        """
        await self.event_store.log_event(
            "system_startup",
            {"component": "LLMBridgeCore", "status": "initializing"}
        )
        
        # Load registry config if available
        try:
            registry_data = self.config_provider.get("registry")
            if registry_data:
                self._registry_config = RegistrySchema.build_from_yaml_data(registry_data)
                self.logger.info(
                    f"Registry loaded: {len(self._registry_config.models)} models, "
                    f"{len(self._registry_config.agents)} agents"
                )
        except Exception as e:
            self.logger.warning(f"Failed to load registry config: {e}")
        
        await self.event_store.log_event(
            "system_startup",
            {"component": "LLMBridgeCore", "status": "initialized"}
        )
    
    async def bridge_message(self, 
                           conversation_id: str, 
                           target_llm_name: str, 
                           message: str, 
                           **kwargs) -> str:
        """
        Bridge a message to the target LLM
        
        Args:
            conversation_id: Unique conversation identifier
            target_llm_name: Name of the target LLM
            message: Message to send
            **kwargs: Additional parameters for routing
            
        Returns:
            Response from the LLM
        """
        # Start telemetry trace
        trace_id = await self.telemetry.trace_start(
            "bridge_message",
            {
                "conversation_id": conversation_id,
                "target_llm": target_llm_name,
                "message_length": len(message)
            }
        )
        
        # Log event
        await self.event_store.log_event(
            "bridge_request",
            {
                "conversation_id": conversation_id,
                "target_llm": target_llm_name,
                "message_length": len(message)
            }
        )
        
        try:
            # Route the message
            response = await self.router.route_message(
                conversation_id=conversation_id,
                target_llm_name=target_llm_name,
                prompt=message,
                **kwargs
            )
            
            # End trace with success
            await self.telemetry.trace_end(trace_id, {"response_length": len(response)})
            
            # Log success
            await self.event_store.log_event(
                "bridge_success",
                {
                    "conversation_id": conversation_id,
                    "response_length": len(response)
                }
            )
            
            return response
            
        except Exception as e:
            # End trace with error
            await self.telemetry.trace_end(trace_id, error=str(e))
            
            # Log error
            await self.event_store.log_event(
                "bridge_error",
                {
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )
            
            # Re-raise the exception
            raise
    
    def get_available_models(self) -> list[str]:
        """
        Get list of available models
        
        Returns:
            List of model names
        """
        return list(self.config_provider.get_all_models().keys())
    
    def get_registry_config(self) -> Optional[RegistrySchema]:
        """
        Get the loaded registry configuration
        
        Returns:
            Registry configuration or None if not loaded
        """
        return self._registry_config
    
    async def execute_workflow_from_file(self, workflow_path: str) -> dict:
        """
        Execute a workflow from a YAML file
        
        Args:
            workflow_path: Path to the workflow file
            
        Returns:
            Workflow execution results
        """
        # This method would need the WorkflowOrchestrator to be injected as well
        # For now, we'll raise NotImplementedError
        raise NotImplementedError(
            "WorkflowOrchestrator needs to be injected for workflow execution"
        )
    
    async def shutdown(self) -> None:
        """
        Graceful shutdown of the bridge
        """
        await self.event_store.log_event(
            "system_shutdown",
            {"component": "LLMBridgeCore"}
        )
        
        self.logger.info("LLMBridgeCore shutdown complete")