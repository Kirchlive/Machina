# llm_bridge/routing/router.py

# Importiere die Adapter-Klassen, um ihren Typ prüfen zu können
from ..adapters.openrouter_adapter import OpenRouterAdapter
from ..adapters.claude_adapter import ClaudeAdapter
from ..adapters.gemini_adapter import GeminiAdapter
from ..adapters.universal_adapter import UniversalAdapter
from ..orchestration.conversation_state import ConversationStateMachine  # <-- NEU
from ..orchestration.circuit_breaker import CircuitBreakerError  # <-- NEU: Import für spezifische Exception

# --- NEU: Redis Cache Imports ---
import os
import redis.asyncio as redis
import hashlib
import json
from typing import Optional
# --- Ende NEU ---

class Router:
    def __init__(self, adapters: dict, circuit_breakers: dict, model_config: dict = None, event_store = None, langfuse = None):
        self.adapters = adapters
        self.circuit_breakers = circuit_breakers
        self.model_config = model_config or {}
        self.active_conversations = {}  # Ersetzt die einfache conversation_history
        self.event_store = event_store
        self.langfuse = langfuse
        
        # --- NEU: Redis Cache Initialisierung ---
        self.cache: Optional[redis.Redis] = None
        self._init_cache()
    
    def _init_cache(self):
        """Initialisiert Redis Cache-Verbindung"""
        try:
            # Flexibel: Entweder REDIS_URL oder einzelne Parameter
            redis_url = os.getenv("REDIS_URL")
            
            if redis_url:
                self.cache = redis.from_url(redis_url, decode_responses=True)
                print(f"🔄 Redis Cache initialisiert: {redis_url}")
            else:
                # Fallback auf einzelne Parameter
                redis_host = os.getenv('REDIS_HOST', 'localhost')
                redis_port = int(os.getenv('REDIS_PORT', '6379'))
                redis_db = int(os.getenv('REDIS_DB', '0'))
                
                self.cache = redis.Redis(
                    host=redis_host, 
                    port=redis_port, 
                    db=redis_db, 
                    decode_responses=True
                )
                print(f"🔄 Redis Cache initialisiert: {redis_host}:{redis_port}/{redis_db}")
                
        except Exception as e:
            print(f"⚠️ Redis Cache nicht verfügbar: {e}")
            print("⚠️ Caching ist deaktiviert. Bridge läuft ohne Cache.")
            self.cache = None

    async def route_message(self, conversation_id: str, target_llm_name: str, prompt: str, **kwargs) -> str:
        # --- NEU: Cache-Logik VOR dem LLM-Aufruf ---
        cached_response = None
        cache_key = None
        
        if self.cache:
            try:
                # Teste Redis-Verbindung beim ersten Aufruf
                await self.cache.ping()
                
                # Erstelle einen eindeutigen Cache-Schlüssel
                cache_data = f"{target_llm_name}:{prompt}:{json.dumps(kwargs, sort_keys=True)}"
                cache_key = f"llm_response:{hashlib.sha256(cache_data.encode()).hexdigest()}"
                
                # Prüfe Cache
                cached_response = await self.cache.get(cache_key)
                if cached_response:
                    print(f"✅ Cache-Hit für {target_llm_name[:20]}...")
                    # Parse JSON und gib direkt zurück
                    return json.loads(cached_response)
                else:
                    print(f"🔍 Cache-Miss für {target_llm_name[:20]}...")
                    
            except Exception as e:
                print(f"⚠️ Cache-Fehler: {e}")
                # Bei Cache-Fehler einfach weitermachen
        
        # --- NEU: LangFuse v3 minimale funktionsfähige API ---
        generation = None
        if self.langfuse:
            # Starte die Generation nur mit den minimal notwendigen Parametern
            generation = self.langfuse.start_generation(
                name=f"call-{target_llm_name}",
                input=prompt,
                model=target_llm_name,
                metadata={"conversation_id": conversation_id, "target_llm": target_llm_name}
            )
        # --- Ende NEU ---
        
        # Hole die State Machine für diese Konversation oder erstelle eine neue
        state_machine = self.active_conversations.setdefault(
            conversation_id,
            ConversationStateMachine(conversation_id)
        )

        # Prüfe, ob der Übergang erlaubt ist
        # Für Mission Control (mission_* conversation_ids) erlaube Wiederholungen
        allow_repeats = conversation_id.startswith('mission_')
        if not state_machine.transition_to(target_llm_name, self.event_store, allow_repeats=allow_repeats):
            raise Exception(f"Invalid state transition for conversation '{conversation_id}'.")

        adapter_name, model_identifier = self._resolve_target(target_llm_name)
        if not adapter_name:
            raise Exception(f"Could not resolve target '{target_llm_name}'.")

        target_adapter = self.adapters.get(adapter_name)
        breaker = self.circuit_breakers.get(adapter_name)
        if not target_adapter or not breaker:
            raise Exception(f"Adapter or Circuit Breaker for '{adapter_name}' not found.")

        kwargs['model'] = model_identifier
        
        # Log den API-Aufruf
        if self.event_store:
            await self.event_store.log_adapter_call(
                adapter_name=adapter_name,
                model_name=model_identifier,
                conversation_id=conversation_id,
                prompt_length=len(prompt),
                success=False  # Wird bei Erfolg aktualisiert
            )
        
        
        try:
            # Prüfe ob es ein Universal Adapter (CLI/Browser) oder klassischer API-Adapter ist
            if isinstance(target_adapter, UniversalAdapter):
                # Für Universal Adapter: verwende chat_completion
                messages = [{"role": "user", "content": prompt}]
                chat_response = await breaker.execute(target_adapter.chat_completion(messages, **kwargs))
                response = chat_response["choices"][0]["message"]["content"]
            else:
                # Für klassische API-Adapter: verwende send mit model-Parameter
                # Sichere, dass der korrekte model_identifier verwendet wird
                kwargs['model'] = model_identifier
                
                # Lese die base_url aus der Konfiguration, falls vorhanden (für Ollama)
                model_config = self.model_config.get(target_llm_name, {})
                if 'base_url' in model_config:
                    kwargs['base_url'] = model_config['base_url']
                
                response = await breaker.execute(target_adapter.send(prompt, **kwargs))
            
            # --- NEU: LangFuse v3 Generation bei Erfolg aktualisieren ---
            if generation:
                generation.update(output=response)
            # --- Ende NEU ---
            
            # Log erfolgreichen API-Aufruf
            if self.event_store:
                await self.event_store.log_adapter_call(
                    adapter_name=adapter_name,
                    model_name=model_identifier,
                    conversation_id=conversation_id,
                    prompt_length=len(prompt),
                    success=True,
                    response_length=len(response) if response else 0
                )
            
            # Den neuen Zustand nach erfolgreicher Antwort festhalten
            state_machine.record_response(from_llm_name=target_llm_name, event_store=self.event_store)
            
            # --- NEU: Response im Cache speichern ---
            if self.cache and cache_key and response:
                try:
                    # Cache für 24 Stunden (86400 Sekunden)
                    cache_ttl = int(os.getenv("CACHE_TTL_SECONDS", "86400"))
                    await self.cache.set(cache_key, json.dumps(response), ex=cache_ttl)
                    print(f"💾 Response im Cache gespeichert (TTL: {cache_ttl}s)")
                except Exception as e:
                    print(f"⚠️ Cache-Speicher-Fehler: {e}")
                    # Bei Cache-Fehler einfach weitermachen
            # --- Ende NEU ---
            
            return response
            
        except CircuitBreakerError as e:
            # ▶️ Spezifische Fehlerbehandlung für einen offenen Circuit Breaker
            print(f"[Router] Anfrage an '{target_llm_name}' durch offenen Circuit Breaker blockiert. Grund: {e}")
            
            # LangFuse Generation bei Circuit Breaker Fehler aktualisieren
            if generation:
                generation.update(level="ERROR", status_message=f"Circuit Breaker Open: {str(e)}")
            
            # Log Circuit Breaker Event
            if self.event_store:
                await self.event_store.log_adapter_call(
                    adapter_name=adapter_name,
                    model_name=model_identifier,
                    conversation_id=conversation_id,
                    prompt_length=len(prompt),
                    success=False,
                    error_message=f"Circuit Breaker Open: {str(e)}"
                )
            
            # Re-raise mit mehr Kontext für API-Layer
            raise e
            
        except Exception as e:
            # --- NEU: LangFuse v3 Generation bei Fehler aktualisieren ---
            if generation:
                generation.update(level="ERROR", status_message=str(e))
            # --- Ende NEU ---
            
            # Log fehlgeschlagenen API-Aufruf
            if self.event_store:
                await self.event_store.log_adapter_call(
                    adapter_name=adapter_name,
                    model_name=model_identifier,
                    conversation_id=conversation_id,
                    prompt_length=len(prompt),
                    success=False,
                    error_message=str(e)
                )
            raise e
        finally:
            # Stelle sicher, dass die Generation immer ordnungsgemäß beendet wird
            if generation:
                generation.end()
    
    # Die alte _is_loop Methode wird entfernt, da die State Machine dies übernimmt.
    
    def _resolve_target(self, target_name: str) -> tuple[str | None, str | None]:
        """
        Findet den korrekten Adapter-Dienst und den passenden Modell-Identifier,
        basierend auf der Plattform (API vs. CLI/Browser/Desktop).
        """
        if target_name not in self.model_config:
            return None, None

        config = self.model_config[target_name]
        
        # NEUE, KORREKTE LOGIK
        if config.get('platform', 'api') != 'api':
            # Dies ist ein Plattform-Adapter (CLI, Browser etc.)
            # Der Adapter ist direkt unter target_name registriert
            model_identifier = config.get("command") or config.get("tool_name")
            return target_name, model_identifier
        else:
            # Dies ist ein API-basierter Adapter
            adapter_service_name = config.get('adapter_service')
            
            # Den registrierten Adapter für diesen Dienst holen
            active_adapter = self.adapters.get(adapter_service_name)
            if not active_adapter:
                return None, None

            # INTELLIGENTE AUSWAHL für API-Adapter:
            # Prüfen, ob der aktive Adapter ein direkter, nativer Adapter ist
            if isinstance(active_adapter, (ClaudeAdapter, GeminiAdapter)):
                # Ja -> Nutze den 'direct'-Modellnamen
                model_identifier = config.get("model_name_direct")
            else: 
                # Nein -> Nutze den 'openrouter'-Modellnamen, fallback auf 'direct'
                model_identifier = config.get("model_name_openrouter") or config.get("model_name_direct")
                
            return adapter_service_name, model_identifier