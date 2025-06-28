# Datei: llm_bridge/repositories/redis_agent_state_repository.py

import redis.asyncio as redis
from typing import Optional, List
from .agent_state_repository import IAgentStateRepository
from ..orchestration.agent_state import AgentState

# Konstanten für Redis-Schlüssel, um "Magic Strings" zu vermeiden
STATE_KEY_PREFIX = "llm_bridge:mission_state:"
ACTIVE_MISSIONS_SET_KEY = "llm_bridge:active_missions"
MISSION_TTL_SECONDS = 24 * 3600  # Missionen nach 24h automatisch verfallen lassen


class RedisAgentStateRepository(IAgentStateRepository):
    def __init__(self, client: redis.Redis):
        self._client = client

    def _get_key(self, mission_id: str) -> str:
        return f"{STATE_KEY_PREFIX}{mission_id}"

    async def save(self, state: AgentState) -> None:
        """
        Speichert den AgentState transaktional in Redis.
        - Der vollständige State wird als JSON in einem String gespeichert.
        - Die Mission-ID wird zu einem Set aktiver Missionen hinzugefügt oder daraus entfernt.
        """
        key = self._get_key(state.mission_id)
        state_json = state.model_dump_json()

        # Wir verwenden eine Pipeline, um sicherzustellen, dass beide Operationen
        # (Speichern des Zustands und Aktualisieren des Sets) atomar erfolgen.
        async with self._client.pipeline(transaction=True) as pipe:
            # Speichere den Zustand mit einer Verfallszeit
            pipe.set(key, state_json, ex=MISSION_TTL_SECONDS)

            # Aktualisiere das Set der aktiven Missionen
            if state.status in ["PENDING", "PLANNING", "RUNNING", "AWAITING_HUMAN_INPUT"]:
                pipe.sadd(ACTIVE_MISSIONS_SET_KEY, state.mission_id)
            else:  # COMPLETED, ERROR
                pipe.srem(ACTIVE_MISSIONS_SET_KEY, state.mission_id)
            
            await pipe.execute()

    async def get_by_id(self, mission_id: str) -> Optional[AgentState]:
        key = self._get_key(mission_id)
        data = await self._client.get(key)
        if data:
            return AgentState.model_validate_json(data)
        return None

    async def delete(self, mission_id: str) -> None:
        key = self._get_key(mission_id)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.delete(key)
            pipe.srem(ACTIVE_MISSIONS_SET_KEY, mission_id)
            await pipe.execute()

    async def list_active_ids(self) -> List[str]:
        """
        Liest effizient die IDs aller aktiven Missionen aus dem dedizierten Set.
        Dies vermeidet ein ressourcenintensives "KEYS *" Scanning.
        """
        active_ids = await self._client.smembers(ACTIVE_MISSIONS_SET_KEY)
        # Da decode_responses=True im Redis Client gesetzt ist, sind die Strings bereits dekodiert
        return list(active_ids)