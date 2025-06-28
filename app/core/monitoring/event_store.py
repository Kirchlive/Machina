# llm_bridge/monitoring/event_store.py
import json
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

class EventStore:
    """
    Enterprise Event Store für die vollständige Auditierung aller Bridge-Aktivitäten.
    Speichert Events im JSONL-Format für einfache Analyse und Nachverfolgung.
    """
    
    def __init__(self, log_file: str = "bridge_events.jsonl"):
        self.log_file = Path(log_file)
        self._lock = asyncio.Lock()
        self._ensure_log_file()
        
    def _ensure_log_file(self):
        """Stellt sicher, dass die Log-Datei existiert."""
        if not self.log_file.exists():
            self.log_file.touch()
            
    async def log_event(self, 
                       event_type: str, 
                       component: str, 
                       message: str, 
                       conversation_id: Optional[str] = None,
                       **additional_data):
        """
        Strukturiertes Event-Logging mit vollständigen Metadaten.
        
        Args:
            event_type: Art des Events (INFO, ERROR, STATE_CHANGE, etc.)
            component: Welche Komponente das Event ausgelöst hat
            message: Menschenlesbare Beschreibung
            conversation_id: Optional - ID der betroffenen Konversation
            **additional_data: Beliebige zusätzliche Event-Daten
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "component": component,
            "message": message,
            "conversation_id": conversation_id,
            **additional_data
        }
        
        async with self._lock:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(event, ensure_ascii=False) + '\n')
                
    async def log_adapter_call(self, 
                              adapter_name: str, 
                              model_name: str, 
                              conversation_id: str,
                              prompt_length: int,
                              success: bool,
                              response_length: Optional[int] = None,
                              error_message: Optional[str] = None):
        """Spezielles Logging für LLM-API-Aufrufe."""
        await self.log_event(
            event_type="ADAPTER_CALL",
            component="Router",
            message=f"API call to {adapter_name} with model {model_name}",
            conversation_id=conversation_id,
            adapter_name=adapter_name,
            model_name=model_name,
            prompt_length=prompt_length,
            success=success,
            response_length=response_length,
            error_message=error_message
        )
        
    async def log_state_transition(self, 
                                  conversation_id: str, 
                                  from_state: str, 
                                  to_state: str,
                                  target_llm: Optional[str] = None):
        """Spezielles Logging für State Machine Übergänge."""
        await self.log_event(
            event_type="STATE_TRANSITION",
            component="ConversationStateMachine",
            message=f"State transition: {from_state} -> {to_state}",
            conversation_id=conversation_id,
            from_state=from_state,
            to_state=to_state,
            target_llm=target_llm
        )
        
    async def log_circuit_breaker_event(self, 
                                       adapter_name: str, 
                                       event: str, 
                                       failure_count: Optional[int] = None):
        """Spezielles Logging für Circuit Breaker Events."""
        await self.log_event(
            event_type="CIRCUIT_BREAKER",
            component="CircuitBreaker",
            message=f"Circuit breaker {event} for {adapter_name}",
            adapter_name=adapter_name,
            breaker_event=event,
            failure_count=failure_count
        )
        
    async def query_events(self, 
                          conversation_id: Optional[str] = None,
                          event_type: Optional[str] = None,
                          component: Optional[str] = None,
                          limit: int = 100) -> list:
        """
        Einfache Event-Abfrage für Debugging und Monitoring.
        Lädt Events aus der JSONL-Datei und filtert sie.
        """
        events = []
        
        if not self.log_file.exists():
            return events
            
        with open(self.log_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                if len(events) >= limit:
                    break
                    
                try:
                    event = json.loads(line.strip())
                    
                    # Filter anwenden
                    if conversation_id and event.get('conversation_id') != conversation_id:
                        continue
                    if event_type and event.get('event_type') != event_type:
                        continue
                    if component and event.get('component') != component:
                        continue
                        
                    events.append(event)
                    
                except json.JSONDecodeError:
                    # Defekte Zeile überspringen
                    continue
                    
        return events[-limit:]  # Neueste Events zuerst