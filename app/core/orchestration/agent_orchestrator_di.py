# llm_bridge/orchestration/agent_orchestrator_di.py
"""
Refactored AgentOrchestrator with Dependency Injection

This version uses injected dependencies for better testability and loose coupling.
"""

import json
import yaml
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging

from .agent_state import AgentState, StateManager
from .data_models import TaskPlan, ResearchReport, FinalReport, QAReport, HumanRequest, QualityAssessment
from ..core_di import LLMBridgeCore
from ..tools.registry import TOOL_REGISTRY, HumanInterventionRequired
from ..di.interfaces import (
    IStateRepository,
    IEventStore,
    ITelemetry,
    IConfigurationProvider,
    ILogger
)

class AgentOrchestrator:
    """
    Orchestrates multi-agent workflows with dependency injection
    
    All dependencies are injected, making the orchestrator
    more testable and loosely coupled.
    """
    
    def __init__(self,
                 bridge: LLMBridgeCore,
                 state_repository: IStateRepository,
                 event_store: IEventStore,
                 telemetry: ITelemetry,
                 config_provider: IConfigurationProvider,
                 logger: Optional[ILogger] = None):
        """
        Initialize the orchestrator with injected dependencies
        
        Args:
            bridge: LLM bridge for agent communication
            state_repository: Repository for state persistence
            event_store: Event logging service
            telemetry: Telemetry service
            config_provider: Configuration provider
            logger: Optional logger
        """
        self.bridge = bridge
        self.state_repository = state_repository
        self.event_store = event_store
        self.telemetry = telemetry
        self.config_provider = config_provider
        self.logger = logger or logging.getLogger(__name__)
        
        # Load configurations
        self.crews_config = config_provider.get('crews', {})
        self.agents_config = config_provider.get('agents', {})
        self.mission_templates = config_provider.get('mission_templates', {})
        
        self.logger.info(
            f"AgentOrchestrator initialized with {len(self.crews_config)} crews "
            f"and {len(self.agents_config)} agents"
        )
    
    async def execute_mission(self, 
                            crew_name: str, 
                            goal: str, 
                            parameters: Optional[Dict[str, Any]] = None) -> AgentState:
        """
        Execute a complete mission with the specified crew
        
        Args:
            crew_name: Name of the crew from configuration
            goal: High-level mission goal
            parameters: Optional mission parameters
            
        Returns:
            Final state after execution
        """
        # Start telemetry trace
        trace_id = await self.telemetry.trace_start(
            "execute_mission",
            {
                "crew_name": crew_name,
                "goal": goal,
                "parameters": parameters
            }
        )
        
        # Validate crew
        if crew_name not in self.crews_config:
            await self.telemetry.trace_end(trace_id, error=f"Crew '{crew_name}' not found")
            raise ValueError(f"Crew '{crew_name}' not found in configuration")
        
        crew_config = self.crews_config[crew_name]
        state = StateManager.create_mission_state(crew_name, goal)
        
        # Log mission start
        await self.event_store.log_event(
            "mission_start",
            {
                "mission_id": state.mission_id,
                "crew_name": crew_name,
                "goal": goal
            }
        )
        
        try:
            # Save initial state
            state.add_history_entry(f"Mission '{state.mission_id}' created.")
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            self.logger.info(f"Starting mission {state.mission_id} with crew {crew_name}")
            
            # Phase 1: Planning
            await self._planning_phase(state, crew_config, parameters)
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # Phase 2: Execution
            await self._execution_phase(state, crew_config)
            
            # Phase 3: Synthesis
            await self._synthesis_phase(state, crew_config)
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # Complete mission
            state.complete_execution()
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # Log completion
            await self.event_store.log_event(
                "mission_complete",
                {
                    "mission_id": state.mission_id,
                    "duration": state.get_execution_time()
                }
            )
            
            # End trace
            await self.telemetry.trace_end(
                trace_id,
                {"status": "completed", "mission_id": state.mission_id}
            )
            
            self.logger.info(f"Mission {state.mission_id} completed successfully")
            
        except HumanInterventionRequired as e:
            # Handle human intervention
            self.logger.info(
                f"Mission {state.mission_id} paused: "
                f"Agent {e.request_details.agent_name} requires human input"
            )
            
            # Log pause event
            await self.event_store.log_event(
                "mission_paused",
                {
                    "mission_id": state.mission_id,
                    "agent": e.request_details.agent_name,
                    "request": e.request_details.request
                }
            )
            
            # Save paused state
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # End trace with pause status
            await self.telemetry.trace_end(
                trace_id,
                {"status": "paused", "reason": "human_intervention"}
            )
            
            return state
            
        except Exception as e:
            # Handle error
            error_msg = f"Mission execution failed: {str(e)}"
            self.logger.error(error_msg)
            
            # Mark error in state
            state.mark_error(error_msg)
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # Log error
            await self.event_store.log_event(
                "mission_error",
                {
                    "mission_id": state.mission_id,
                    "error": str(e)
                }
            )
            
            # End trace with error
            await self.telemetry.trace_end(trace_id, error=str(e))
            
            raise
        
        return state
    
    async def resume_mission(self, 
                           mission_id: str, 
                           human_response: str) -> AgentState:
        """
        Resume a paused mission with human input
        
        Args:
            mission_id: ID of the paused mission
            human_response: Human response to the request
            
        Returns:
            Final state after completion
        """
        # Start telemetry trace
        trace_id = await self.telemetry.trace_start(
            "resume_mission",
            {
                "mission_id": mission_id,
                "response_length": len(human_response)
            }
        )
        
        try:
            # Load state
            state_dict = await self.state_repository.load_state(mission_id)
            if not state_dict:
                raise ValueError(f"Mission {mission_id} not found")
            
            state = AgentState.from_dict(state_dict)
            
            # Log resume event
            await self.event_store.log_event(
                "mission_resumed",
                {"mission_id": mission_id}
            )
            
            # Find paused request
            paused_request = state.get_paused_human_request()
            if not paused_request:
                raise ValueError(f"No paused human request in mission {mission_id}")
            
            # Complete the request
            state.complete_human_request(paused_request.request_id, human_response)
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # Get crew config
            crew_config = self.crews_config.get(state.crew_name)
            if not crew_config:
                raise ValueError(f"Crew config not found for {state.crew_name}")
            
            # Continue execution
            await self._execution_phase(state, crew_config)
            
            # Synthesis phase
            await self._synthesis_phase(state, crew_config)
            
            # Complete mission
            state.complete_execution()
            await self.state_repository.save_state(state.mission_id, state.to_dict())
            
            # End trace
            await self.telemetry.trace_end(
                trace_id,
                {"status": "completed", "mission_id": mission_id}
            )
            
            return state
            
        except Exception as e:
            # End trace with error
            await self.telemetry.trace_end(trace_id, error=str(e))
            raise
    
    async def _planning_phase(self, 
                            state: AgentState, 
                            crew_config: Dict[str, Any], 
                            parameters: Optional[Dict[str, Any]]) -> None:
        """Execute the planning phase"""
        # Implementation would be similar to original but using injected services
        pass
    
    async def _execution_phase(self, 
                             state: AgentState, 
                             crew_config: Dict[str, Any]) -> None:
        """Execute the main workflow phase"""
        # Implementation would be similar to original but using injected services
        pass
    
    async def _synthesis_phase(self, 
                             state: AgentState, 
                             crew_config: Dict[str, Any]) -> None:
        """Execute the synthesis phase"""
        # Implementation would be similar to original but using injected services
        pass