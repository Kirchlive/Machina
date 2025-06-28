"""
Event Store Service Implementation

Provides event logging and monitoring capabilities with async support.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import logging
import json
from collections import deque
import asyncio
from app.core.di.interfaces import IEventStore

class EventStoreService(IEventStore):
    """
    Concrete implementation of IEventStore
    
    Provides in-memory event storage with:
    - Async event logging
    - Event filtering by type
    - Configurable retention limits
    - JSON serialization for complex data
    """
    
    def __init__(self, 
                 max_events: int = 10000,
                 logger: Optional[logging.Logger] = None,
                 persist_to_file: Optional[str] = None):
        """
        Initialize the event store
        
        Args:
            max_events: Maximum number of events to keep in memory
            logger: Logger instance to use
            persist_to_file: Optional file path to persist events
        """
        self._events: deque = deque(maxlen=max_events)
        self._logger = logger or logging.getLogger(__name__)
        self._persist_file = persist_to_file
        self._lock = asyncio.Lock()
        self._event_handlers: Dict[str, List[callable]] = {}
        
    async def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log an event with associated data"""
        async with self._lock:
            event = {
                'timestamp': datetime.utcnow().isoformat(),
                'type': event_type,
                'data': data
            }
            
            self._events.append(event)
            
            # Log to standard logger
            self._logger.info(
                f"Event: {event_type}",
                extra={'event_data': data}
            )
            
            # Persist to file if configured
            if self._persist_file:
                await self._persist_event(event)
            
            # Trigger event handlers
            await self._trigger_handlers(event_type, event)
    
    async def get_events(self, 
                        event_type: Optional[str] = None, 
                        limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieve logged events with optional filtering"""
        async with self._lock:
            if event_type:
                filtered = [e for e in self._events if e['type'] == event_type]
                return list(filtered)[-limit:]
            else:
                return list(self._events)[-limit:]
    
    async def _persist_event(self, event: Dict[str, Any]) -> None:
        """Persist event to file"""
        try:
            # Append event as JSON line
            with open(self._persist_file, 'a') as f:
                f.write(json.dumps(event) + '\n')
        except Exception as e:
            self._logger.error(f"Failed to persist event: {e}")
    
    async def _trigger_handlers(self, event_type: str, event: Dict[str, Any]) -> None:
        """Trigger registered event handlers"""
        handlers = self._event_handlers.get(event_type, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                self._logger.error(f"Event handler error: {e}")
    
    def register_handler(self, event_type: str, handler: callable) -> None:
        """Register an event handler for a specific event type"""
        if event_type not in self._event_handlers:
            self._event_handlers[event_type] = []
        self._event_handlers[event_type].append(handler)
    
    async def clear_events(self, event_type: Optional[str] = None) -> None:
        """Clear events from memory"""
        async with self._lock:
            if event_type:
                # Filter out events of the specified type
                self._events = deque(
                    (e for e in self._events if e['type'] != event_type),
                    maxlen=self._events.maxlen
                )
            else:
                self._events.clear()
    
    async def get_event_stats(self) -> Dict[str, Any]:
        """Get statistics about stored events"""
        async with self._lock:
            event_counts = {}
            for event in self._events:
                event_type = event['type']
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
            
            return {
                'total_events': len(self._events),
                'event_types': event_counts,
                'max_capacity': self._events.maxlen,
                'oldest_event': self._events[0]['timestamp'] if self._events else None,
                'newest_event': self._events[-1]['timestamp'] if self._events else None
            }

class LangfuseEventStore(EventStoreService):
    """
    Extended event store with Langfuse integration
    
    This maintains compatibility with existing Langfuse usage
    while providing the standard event store interface.
    """
    
    def __init__(self, 
                 langfuse_client: Optional[Any] = None,
                 **kwargs):
        """Initialize with optional Langfuse client"""
        super().__init__(**kwargs)
        self._langfuse = langfuse_client
        
    async def log_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Log event to both local store and Langfuse"""
        # Log to local store
        await super().log_event(event_type, data)
        
        # Log to Langfuse if available
        if self._langfuse:
            try:
                # Map event types to Langfuse methods
                if event_type == "llm_request":
                    self._langfuse.generation(
                        name=data.get('model', 'unknown'),
                        input=data.get('prompt'),
                        output=data.get('response'),
                        metadata=data
                    )
                elif event_type == "error":
                    self._langfuse.event(
                        name="error",
                        level="error",
                        metadata=data
                    )
                else:
                    self._langfuse.event(
                        name=event_type,
                        metadata=data
                    )
            except Exception as e:
                self._logger.error(f"Failed to log to Langfuse: {e}")