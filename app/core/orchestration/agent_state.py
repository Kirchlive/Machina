# llm_bridge/orchestration/agent_state.py
"""
Definiert das State-Objekt, das den Fortschritt eines Agenten-Workflows verwaltet.
Inspiriert von LangGraph's State-Konzept.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
from datetime import datetime
import uuid
import json
from .data_models import TaskPlan, MissionStatus, HumanRequest

class AgentState(BaseModel):
    """Verwaltet den Zustand einer Multi-Agenten-Mission."""
    
    # Identifikation & Metadaten
    mission_id: str = Field(default_factory=lambda: f"mission_{uuid.uuid4().hex[:8]}")
    crew_name: str = Field(description="Name der ausführenden Crew")
    high_level_goal: str = Field(description="Das ursprüngliche, hochrangige Ziel")
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Planung & Ausführung
    task_plan: Optional[List[TaskPlan]] = Field(default=None, description="Strukturierter Aufgabenplan")
    current_node: Optional[str] = Field(default=None, description="Aktuell aktiver Agent/Knoten")
    completed_nodes: List[str] = Field(default_factory=list, description="Bereits abgeschlossene Knoten")
    
    # Ergebnisse & Daten
    results: Dict[str, Any] = Field(default_factory=dict, description="Strukturierte Ergebnisse pro Agent")
    intermediate_data: Dict[str, Any] = Field(default_factory=dict, description="Zwischenergebnisse und temporäre Daten")
    
    # Status & Verlauf
    status: str = Field(default="PENDING", description="PENDING, PLANNING, RUNNING, AWAITING_HUMAN_INPUT, COMPLETED, ERROR")
    progress_percentage: float = Field(default=0.0, ge=0, le=100)
    history: List[str] = Field(default_factory=list, description="Chronologisches Log wichtiger Schritte")
    error_messages: List[str] = Field(default_factory=list, description="Aufgetretene Fehler")
    
    # ▶️ Human-in-the-Loop Support
    active_human_request: Optional[HumanRequest] = Field(
        default=None, 
        description="Die aktive Anfrage an einen Menschen, falls der Status AWAITING_HUMAN_INPUT ist."
    )
    
    # Timing & Performance
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    execution_time_seconds: Optional[float] = Field(default=None)
    
    def start_execution(self):
        """Markiert den Beginn der Ausführung."""
        self.started_at = datetime.now()
        self.status = "RUNNING"
        self.add_history_entry("Mission execution started")
    
    def complete_execution(self):
        """Markiert die erfolgreiche Beendigung."""
        self.completed_at = datetime.now()
        self.status = "COMPLETED"
        self.progress_percentage = 100.0
        if self.started_at:
            self.execution_time_seconds = (self.completed_at - self.started_at).total_seconds()
        self.add_history_entry("Mission execution completed successfully")
    
    def mark_error(self, error_message: str):
        """Markiert einen Fehler."""
        self.status = "ERROR"
        self.error_messages.append(f"{datetime.now().isoformat()}: {error_message}")
        self.add_history_entry(f"ERROR: {error_message}")
    
    def add_history_entry(self, message: str):
        """Fügt einen Eintrag zum Verlauf hinzu."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.history.append(f"[{timestamp}] {message}")
    
    def set_current_node(self, node_name: str):
        """Setzt den aktuell aktiven Knoten."""
        if self.current_node and self.current_node not in self.completed_nodes:
            self.completed_nodes.append(self.current_node)
        self.current_node = node_name
        self.add_history_entry(f"Switched to node: {node_name}")
        
        # Update progress
        if self.task_plan:
            completed_tasks = len(self.completed_nodes)
            total_tasks = len(self.task_plan)
            self.progress_percentage = min(95.0, (completed_tasks / total_tasks) * 100)
    
    def store_result(self, agent_name: str, result: Any, result_type: str = "output"):
        """Speichert ein Ergebnis eines Agenten."""
        if agent_name not in self.results:
            self.results[agent_name] = {}
        
        self.results[agent_name][result_type] = result
        self.add_history_entry(f"Stored {result_type} result for {agent_name}")
    
    def get_result(self, agent_name: str, result_type: str = "output") -> Any:
        """Holt ein gespeichertes Ergebnis."""
        return self.results.get(agent_name, {}).get(result_type)
    
    def get_latest_result(self) -> Any:
        """Holt das neueste Ergebnis vom zuletzt abgeschlossenen Agenten."""
        if not self.completed_nodes:
            return None
        
        latest_agent = self.completed_nodes[-1]
        return self.get_result(latest_agent, "output")
    
    def to_status_update(self) -> MissionStatus:
        """Erstellt ein Status-Update-Objekt."""
        return MissionStatus(
            mission_id=self.mission_id,
            current_step=self.current_node or "Not started",
            progress_percentage=self.progress_percentage,
            status=self.status,
            message=self.history[-1] if self.history else None
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialisiert den State zu einem Dictionary."""
        return self.model_dump()
    
    def get_summary(self) -> str:
        """Erstellt eine kompakte Zusammenfassung des aktuellen Zustands."""
        summary_parts = [
            f"Mission: {self.mission_id}",
            f"Goal: {self.high_level_goal[:100]}{'...' if len(self.high_level_goal) > 100 else ''}",
            f"Status: {self.status}",
            f"Progress: {self.progress_percentage:.1f}%",
            f"Current: {self.current_node or 'None'}",
            f"Completed: {len(self.completed_nodes)} nodes"
        ]
        
        if self.error_messages:
            summary_parts.append(f"Errors: {len(self.error_messages)}")
        
        return " | ".join(summary_parts)
    
    def to_json_serializable(self) -> Dict[str, Any]:
        """Konvertiert AgentState zu JSON-serialisierbarer Form."""
        data = self.model_dump()
        
        # Konvertiere datetime-Objekte zu ISO-Strings
        if self.created_at:
            data['created_at'] = self.created_at.isoformat()
        if self.started_at:
            data['started_at'] = self.started_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        
        # Konvertiere results rekursiv
        data['results'] = self._serialize_results(data['results'])
        
        return data
    
    def _serialize_results(self, obj: Any) -> Any:
        """Serialisiert results rekursiv, um datetime-Objekte zu handhaben."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._serialize_results(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_results(item) for item in obj]
        elif hasattr(obj, 'model_dump'):
            # Pydantic-Objekte
            return self._serialize_results(obj.model_dump())
        else:
            return obj

class StateManager:
    """Utility-Klasse für erweiterte State-Management-Operationen."""
    
    @staticmethod
    def create_mission_state(crew_name: str, goal: str) -> AgentState:
        """Erstellt einen neuen Mission-State."""
        return AgentState(
            crew_name=crew_name,
            high_level_goal=goal,
            status="PENDING"
        )
    
    @staticmethod
    def merge_states(primary: AgentState, secondary: AgentState) -> AgentState:
        """Führt zwei States zusammen (für komplexe Workflows)."""
        # Einfache Implementierung - kann erweitert werden
        primary.intermediate_data.update(secondary.intermediate_data)
        primary.history.extend(secondary.history)
        return primary
    
    @staticmethod
    def validate_state_transition(current_state: AgentState, next_node: str) -> bool:
        """Validiert, ob ein State-Übergang erlaubt ist."""
        # Basis-Validierung - kann erweitert werden
        if current_state.status == "ERROR":
            return False
        if next_node in current_state.completed_nodes:
            return False
        return True