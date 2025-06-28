"""
In-memory implementation of the Agent State Repository

This implementation is useful for development and testing
when Redis is not available.
"""

from typing import Dict, List, Optional
import asyncio
from datetime import datetime, timedelta

from ..orchestration.agent_state import AgentState
from .agent_state_repository import IAgentStateRepository


class InMemoryAgentStateRepository(IAgentStateRepository):
    """
    In-memory implementation of agent state repository.
    
    WARNING: This implementation does NOT persist data across restarts!
    Use only for development and testing.
    """
    
    def __init__(self):
        self._states: Dict[str, AgentState] = {}
        self._active_ids: set[str] = set()
        self._lock = asyncio.Lock()
        
    async def save(self, state: AgentState) -> None:
        """Save agent state to memory"""
        async with self._lock:
            self._states[state.mission_id] = state
            
            # Update active IDs based on status
            if state.status in ["RUNNING", "AWAITING_HUMAN_INPUT", "PLANNING"]:
                self._active_ids.add(state.mission_id)
            else:
                self._active_ids.discard(state.mission_id)
                
    async def get_by_id(self, mission_id: str) -> Optional[AgentState]:
        """Get agent state by mission ID"""
        async with self._lock:
            return self._states.get(mission_id)
            
    async def delete(self, mission_id: str) -> None:
        """Delete agent state"""
        async with self._lock:
            self._states.pop(mission_id, None)
            self._active_ids.discard(mission_id)
            
    async def list_active_ids(self) -> List[str]:
        """List all active mission IDs"""
        async with self._lock:
            return list(self._active_ids)
            
    async def cleanup_old_states(self, older_than_hours: int = 24) -> int:
        """Clean up old completed states"""
        async with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=older_than_hours)
            to_delete = []
            
            for mission_id, state in self._states.items():
                if (state.status in ["COMPLETED", "ERROR"] and 
                    state.completed_at and 
                    state.completed_at < cutoff_time):
                    to_delete.append(mission_id)
                    
            for mission_id in to_delete:
                del self._states[mission_id]
                
            return len(to_delete)