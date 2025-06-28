# Datei: llm_bridge/repositories/agent_state_repository.py

from abc import ABC, abstractmethod
from typing import Optional, List
from ..orchestration.agent_state import AgentState  # Stellen Sie sicher, dass der Import-Pfad korrekt ist


class IAgentStateRepository(ABC):
    """
    Abstrakte Schnittstelle für die Speicherung und den Abruf von AgentState-Objekten.
    Dies entkoppelt die Kernlogik von der konkreten Datenbankimplementierung.
    """

    @abstractmethod
    async def save(self, state: AgentState) -> None:
        """
        Speichert einen AgentState. Dies sollte eine "Upsert"-Operation sein
        (erstellt, wenn nicht vorhanden, sonst aktualisiert).
        """
        pass

    @abstractmethod
    async def get_by_id(self, mission_id: str) -> Optional[AgentState]:
        """Ruft einen AgentState anhand seiner Missions-ID ab."""
        pass

    @abstractmethod
    async def delete(self, mission_id: str) -> None:
        """Löscht einen AgentState."""
        pass

    @abstractmethod
    async def list_active_ids(self) -> List[str]:
        """
        Gibt eine Liste der IDs aller Missionen zurück, die als 'aktiv' gelten
        (z.B. Status PENDING, RUNNING, AWAITING_HUMAN_INPUT).
        """
        pass