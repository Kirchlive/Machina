import asyncio
import uuid
import os
import traceback
import yaml
import json
from typing import Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from dotenv import load_dotenv
import redis.asyncio as redis
import openai
import anthropic
# TODO: Weitere SDK-Imports für andere Provider hinzufügen
# import google.generativeai as genai

# Wichtig: Wir müssen den Pfad anpassen, damit Python unser llm_bridge-Paket findet
import sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.core.core import LLMBridgeCore
from app.core.orchestration.workflow_engine import WorkflowOrchestrator, WorkflowValidator
from app.core.orchestration.agent_orchestrator import AgentOrchestrator
from app.core.orchestration.agent_state import AgentState
from app.core.repositories.agent_state_repository import IAgentStateRepository
from app.core.repositories.redis_agent_state_repository import RedisAgentStateRepository
from app.core.orchestration.circuit_breaker import CircuitBreakerError
from app.core.utils.http_client import HTTPClientManager

# Import Shutdown Handler - kopiere direkt hier rein
import signal
from typing import List, Callable, Coroutine

class GracefulShutdownHandler:
    """
    Eine Klasse zur Verwaltung eines sauberen Herunterfahrens der Anwendung.
    Sie fängt OS-Signale ab und führt registrierte Cleanup-Aufgaben aus.
    """
    def __init__(self):
        self.is_shutting_down = False
        self._cleanup_callbacks: List[Callable[[], Coroutine]] = []
        self._shutdown_start_time = None

    def register_cleanup(self, callback: Callable[[], Coroutine]):
        """Registriert eine asynchrone Cleanup-Funktion."""
        self._cleanup_callbacks.append(callback)
        print(f"🔧 [SHUTDOWN] Cleanup-Callback registriert: {callback.__name__}")

    def setup_signal_handlers(self):
        """
        Richtet die Signal-Handler für SIGINT (Ctrl+C) und SIGTERM ein.
        """
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, self._signal_handler)
            loop.add_signal_handler(signal.SIGTERM, self._signal_handler)
            print("📡 [SHUTDOWN] Signal-Handler für SIGINT und SIGTERM eingerichtet (Unix-Modus)")
        except NotImplementedError:
            # add_signal_handler ist unter Windows nicht für SIGINT/SIGTERM verfügbar
            # Wir verwenden signal.signal als Fallback
            signal.signal(signal.SIGINT, self._signal_handler_sync)
            signal.signal(signal.SIGTERM, self._signal_handler_sync)
            print("📡 [SHUTDOWN] Signal-Handler für SIGINT und SIGTERM eingerichtet (Windows-Modus)")

    def _signal_handler_sync(self, signum, frame):
        """Synchroner Wrapper für den Signal-Handler (Windows-Kompatibilität)."""
        # Erstelle eine Task für den asynchronen Handler
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.create_task(self._signal_handler(signum))
        else:
            # Fallback für nicht-async Kontexte
            print(f"\n[SHUTDOWN] Signal {signum} erhalten. Sofortiges Beenden.")
            sys.exit(0)
    
    async def _signal_handler(self, signum: int):
        """Leitet den Shutdown-Prozess ein."""
        if self.is_shutting_down:
            print("\n⚠️ [SHUTDOWN] Zweite Aufforderung zum Herunterfahren erhalten. Erzwinge Beendigung.")
            sys.exit(1)
        
        signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        print(f"\n🛑 [SHUTDOWN] Signal {signal_name} erhalten. Starte sauberes Herunterfahren...")
        self.is_shutting_down = True
        self._shutdown_start_time = datetime.now()
        
        # Geben Sie dem Load Balancer (falls vorhanden) Zeit, die Instanz aus der Rotation zu nehmen.
        print("⏳ [SHUTDOWN] Warte 2 Sekunden für Load Balancer...")
        await asyncio.sleep(2)

        await self._run_cleanup()
        
        # Geben Sie laufenden Tasks noch einen Moment Zeit
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            print(f"⏱️ [SHUTDOWN] Warte auf den Abschluss von {len(tasks)} verbleibenden Aufgaben...")
            # Geben Sie den Tasks maximal 10 Sekunden Zeit
            done, pending = await asyncio.wait(tasks, timeout=10.0)
            if pending:
                print(f"⚡ [SHUTDOWN] {len(pending)} Aufgaben wurden nach Timeout abgebrochen.")
                for task in pending:
                    task.cancel()

        shutdown_duration = (datetime.now() - self._shutdown_start_time).total_seconds()
        print(f"🎯 [SHUTDOWN] Herunterfahren abgeschlossen in {shutdown_duration:.2f} Sekunden. Auf Wiedersehen! 👋")
        
        # Setze nur Flag - lasse FastAPI/Uvicorn den Event Loop selbst beenden
        print("🏁 [SHUTDOWN] Shutdown abgeschlossen. Server wird beendet...")

    async def _run_cleanup(self):
        """Führt alle registrierten Cleanup-Callbacks aus."""
        print(f"🧹 [SHUTDOWN] Führe {len(self._cleanup_callbacks)} Cleanup-Aufgaben aus...")
        
        for i, callback in enumerate(reversed(self._cleanup_callbacks), 1):
            try:
                callback_name = getattr(callback, '__name__', str(callback))
                print(f"🔄 [SHUTDOWN] [{i}/{len(self._cleanup_callbacks)}] Führe Cleanup aus: {callback_name}")
                await callback()
                print(f"✅ [SHUTDOWN] [{i}/{len(self._cleanup_callbacks)}] Cleanup erfolgreich: {callback_name}")
            except Exception as e:
                print(f"❌ [SHUTDOWN] Fehler während des Cleanups bei Callback '{callback_name}': {e}")

# Lade die .env-Datei aus dem Hauptverzeichnis
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# JSON Serializer für datetime-Objekte
async def validate_api_keys(bridge: LLMBridgeCore):
    """
    Prüft proaktiv die konfigurierten API-Schlüssel der aktivierten Adapter.
    Warnt bei Problemen, aber bricht den Start nicht ab.
    """
    print("🔑 Starte proaktive API-Schlüssel-Validierung...")
    
    validated_adapters = 0
    failed_adapters = 0
    
    # Wir iterieren durch die geladenen Adapter des Bridge-Cores
    for adapter_name, adapter_instance in bridge.adapters.items():
        try:
            # Spezifische, kostengünstige Prüfungen pro Adapter-Typ
            if "openai" in adapter_name.lower() and os.getenv("OPENAI_API_KEY"):
                try:
                    client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                    models = await client.models.list(timeout=5)
                    if models.data:
                        print(f"   ✅ OpenAI API-Schlüssel ist gültig ({len(models.data)} Modelle verfügbar)")
                        validated_adapters += 1
                    else:
                        print(f"   ⚠️ OpenAI API-Schlüssel antwortet, aber keine Modelle verfügbar")
                        failed_adapters += 1
                except Exception as e:
                    print(f"   ❌ OpenAI API-Schlüssel Validierung fehlgeschlagen: {str(e)[:100]}")
                    failed_adapters += 1
            
            elif "claude" in adapter_name.lower() and os.getenv("CLAUDE_API_KEY"):
                try:
                    client = anthropic.AsyncAnthropic(api_key=os.getenv("CLAUDE_API_KEY"))
                    # Einfache API-Verfügbarkeitsprüfung mit minimaler Message
                    response = await client.messages.create(
                        model="claude-3-haiku-20240307",  # Günstiges Modell für Test
                        max_tokens=1,
                        messages=[{"role": "user", "content": "Hi"}],
                        timeout=5
                    )
                    if response:
                        print(f"   ✅ Anthropic/Claude API-Schlüssel ist gültig")
                        validated_adapters += 1
                except Exception as e:
                    print(f"   ❌ Claude API-Schlüssel Validierung fehlgeschlagen: {str(e)[:100]}")
                    failed_adapters += 1
            
            elif "openrouter" in adapter_name.lower() and os.getenv("OPENROUTER_API_KEY"):
                try:
                    # OpenRouter verwendet OpenAI-kompatible API
                    client = openai.AsyncOpenAI(
                        api_key=os.getenv("OPENROUTER_API_KEY"),
                        base_url="https://openrouter.ai/api/v1"
                    )
                    models = await client.models.list(timeout=5)
                    if models.data:
                        print(f"   ✅ OpenRouter API-Schlüssel ist gültig ({len(models.data)} Modelle verfügbar)")
                        validated_adapters += 1
                    else:
                        print(f"   ⚠️ OpenRouter API-Schlüssel antwortet, aber keine Modelle verfügbar")
                        failed_adapters += 1
                except Exception as e:
                    print(f"   ❌ OpenRouter API-Schlüssel Validierung fehlgeschlagen: {str(e)[:100]}")
                    failed_adapters += 1
            
            else:
                # Für andere Adapter (CLI, Ollama, etc.) keine API-Key-Prüfung nötig
                print(f"   ℹ️ Adapter '{adapter_name}' benötigt keine API-Key-Validierung")
                
        except Exception as e:
            print(f"   ❌ Unerwarteter Fehler bei Adapter '{adapter_name}': {str(e)[:100]}")
            failed_adapters += 1
    
    # Zusammenfassung
    total_checked = validated_adapters + failed_adapters
    if total_checked == 0:
        print("   ℹ️ Keine API-basierten Adapter gefunden - keine Validierung erforderlich")
    else:
        print(f"🔑 API-Key-Validierung abgeschlossen: {validated_adapters}/{total_checked} erfolgreich")
        if failed_adapters > 0:
            print(f"   ⚠️ {failed_adapters} Adapter haben API-Key-Probleme und sind möglicherweise nicht nutzbar")
        else:
            print("   🎉 Alle API-Keys sind gültig und einsatzbereit!")


def json_serializer(obj):
    """Serialisiert datetime-Objekte zu ISO-Strings."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif hasattr(obj, 'model_dump'):
        return json_serializer(obj.model_dump())
    elif isinstance(obj, dict):
        return {k: json_serializer(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [json_serializer(item) for item in obj]
    else:
        return obj

# Helper-Funktion zum Initialisieren der Bridge (mit Plugin-System)
async def initialize_bridge():
    """
    Initialisiert die Bridge mit dem neuen Plugin-System und asynchroner Konfigurationsladung.
    Plugins werden automatisch geladen basierend auf verfügbaren API-Schlüsseln.
    """
    print("🔄 [ASYNC] Initialisiere Bridge mit asynchroner I/O...")
    
    # Bridge erstellen - Plugins und Model Registry werden automatisch asynchron geladen
    bridge = await LLMBridgeCore.create_async()
    
    # Zusätzliche manuelle Adapter-Registrierung für Fallback (falls nötig)
    # Das Plugin-System sollte die meisten Fälle abdecken
    
    if not bridge.adapters:
        raise RuntimeError("CRITICAL: Bridge could not be initialized. No plugins loaded or API keys found.")
        
    print(f"✅ [ASYNC] Registered {len(bridge.adapters)} adapters via Plugin-System: {list(bridge.adapters.keys())}")
    return bridge

# Globale Bridge-Instanz und Orchestratoren
bridge = None
orchestrator = None
agent_orchestrator = None
registry_config = None

# Globale Variablen für Repository und Redis-Client
# Diese werden im Lifespan-Manager initialisiert
redis_client: redis.Redis = None
state_repository: IAgentStateRepository = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup the bridge."""
    global bridge, orchestrator, agent_orchestrator, registry_config
    global redis_client, state_repository
    
    # Graceful Shutdown Handler einrichten
    shutdown_handler = GracefulShutdownHandler()
    shutdown_handler.setup_signal_handlers()
    
    # Bridge initialisieren
    bridge = await initialize_bridge()
    
    # Registry aus validierter Bridge-Konfiguration holen
    registry_config = bridge.get_registry_config().model_dump()  # Konvertiere zu Dict für Kompatibilität
    
    # Orchestratoren initialisieren
    orchestrator = WorkflowOrchestrator(bridge)
    agent_orchestrator = AgentOrchestrator(bridge, registry_config)
    
    print("✅ LLM2LLM-Bridge initialized successfully!")
    print("✅ Workflow-Orchestrator initialized successfully!")
    print("✅ Agent-Orchestrator initialized successfully!")
    print(f"✅ Registry loaded with {len(registry_config.get('agents', {}))} agents and {len(registry_config.get('crews', {}))} crews")
    
    # ▶️ Hinzufügen: API-Schlüssel-Validierung nach der Bridge-Initialisierung
    await validate_api_keys(bridge)
    
    # ▶️ Hinzufügen: Initialisierung von Redis und dem Repository
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        redis_client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)
        await redis_client.ping()  # Verbindung testen
        print("🔗 ✅ Successfully connected to Redis.")
        
        state_repository = RedisAgentStateRepository(redis_client)
        
        # ▶️ Hinzufügen: Wiederherstellungslogik für unterbrochene Missionen
        print("🔍 [STARTUP] Checking for interrupted missions...")
        interrupted_ids = await state_repository.list_active_ids()
        if interrupted_ids:
            print(f"⚠️  Found {len(interrupted_ids)} potentially interrupted missions: {interrupted_ids}")
            for mission_id in interrupted_ids:
                state = await state_repository.get_by_id(mission_id)
                if state:
                    state.mark_error(f"Mission interrupted by server restart at {datetime.now()}.")
                    await state_repository.save(state)
                    print(f"   ❌ Marked mission {mission_id} as ERROR.")
        else:
            print("✅ [SUCCESS] No interrupted missions found.")
            
        # ▶️ Registriere Redis-Cleanup
        async def cleanup_redis():
            """Schließt die Redis-Verbindung sauber."""
            if redis_client:
                print("[CLEANUP] Schließe Redis-Verbindung...")
                try:
                    await redis_client.aclose()  # Verwende aclose() statt close()
                    print("[CLEANUP] Redis-Verbindung geschlossen.")
                except Exception as e:
                    print(f"[CLEANUP] Warnung beim Schließen der Redis-Verbindung: {e}")
        
        shutdown_handler.register_cleanup(cleanup_redis)
        
        # ▶️ Registriere HTTP-Client-Cleanup
        async def cleanup_http_client():
            """Schließt den globalen HTTP-Client sauber."""
            await HTTPClientManager.close_client()
        
        shutdown_handler.register_cleanup(cleanup_http_client)
        print("🌐 [SHUTDOWN] HTTP-Client-Cleanup registriert")
        
    except Exception as e:
        print(f"⚠️  WARNING: Redis connection failed: {str(e)}")
        print("⚠️  Running in degraded mode without persistence!")
        # Fallback auf In-Memory Repository könnte hier implementiert werden
        state_repository = None
    
    # ▶️ Registriere Bridge-Cleanup
    async def cleanup_bridge():
        """Cleanup für die Bridge und ihre Komponenten."""
        if bridge:
            print("[CLEANUP] Führe Bridge-Cleanup durch...")
            # Hier könnten weitere Bridge-spezifische Cleanups durchgeführt werden
            # z.B. Schließen von offenen Adapter-Verbindungen
            for adapter_name, adapter in bridge.adapters.items():
                if hasattr(adapter, 'close'):
                    try:
                        await adapter.close()
                        print(f"[CLEANUP] Adapter '{adapter_name}' geschlossen.")
                    except Exception as e:
                        print(f"[CLEANUP] Fehler beim Schließen von Adapter '{adapter_name}': {e}")
    
    shutdown_handler.register_cleanup(cleanup_bridge)
    
    yield  # Server runs here
    
    # Die Shutdown-Logik wird nun vom Handler übernommen
    print("[LIFESPAN] Application lifespan endet.")

# ==============================================================================
#  1. FastAPI App und Bridge-Initialisierung
# ==============================================================================
app = FastAPI(
    title="LLM2LLM-Bridge API",
    description="Ein universeller Gateway zur Orchestrierung von Konversationen zwischen verschiedenen LLMs.",
    version="1.0.0",
    lifespan=lifespan
)

# ==============================================================================
#  2. Pydantic-Modelle für die API-Datenvalidierung
# ==============================================================================
class NewConversationResponse(BaseModel):
    message: str
    conversation_id: str

class MessageRequest(BaseModel):
    target_llm: str = Field(..., description="Der Kurzname des Ziel-LLMs (z.B. 'gpt4o_mini').")
    prompt: str = Field(..., description="Der Text-Prompt, der an das LLM gesendet werden soll.")
    # In Zukunft könnten hier weitere Parameter wie 'temperature' etc. stehen

class MessageResponse(BaseModel):
    response: str
    conversation_id: str
    target_llm: str

class AvailableModelsResponse(BaseModel):
    models: list[str]

class DetailedModelsResponse(BaseModel):
    models: Dict[str, Dict[str, Any]]
    total_count: int
    registry_info: Dict[str, Any]

class WorkflowRequest(BaseModel):
    workflow: Dict[str, Any] = Field(..., description="Die Workflow-Definition mit name, description und steps")

class WorkflowResponse(BaseModel):
    workflow_id: str
    workflow_name: str
    success: bool
    duration: float
    total_steps: int
    completed_steps: int
    failed_steps: int
    outputs: Dict[str, str]
    error: str = None

# ==============================================================================
#  PHASE 5.2: Multi-Agent Mission Models
# ==============================================================================

class MissionRequest(BaseModel):
    crew_name: str = Field(..., description="Name der zu verwendenden Crew aus registry.yaml")
    goal: str = Field(..., description="Hochrangiges Ziel der Mission")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Optionale Parameter für die Mission")

class TemplateMissionRequest(BaseModel):
    template_name: str = Field(..., description="Name des Mission-Templates")
    parameters: Dict[str, Any] = Field(..., description="Parameter für das Template")

class MissionResponse(BaseModel):
    mission_id: str
    crew_name: str
    goal: str
    status: str
    progress_percentage: float
    execution_time_seconds: float = None
    results: Dict[str, Any] = Field(default_factory=dict)
    history: list[str] = Field(default_factory=list)
    error_messages: list[str] = Field(default_factory=list)
    
class CrewListResponse(BaseModel):
    crews: Dict[str, Dict[str, Any]]
    agents: Dict[str, Dict[str, Any]]
    templates: Dict[str, Dict[str, Any]]

class MissionStatusResponse(BaseModel):
    mission_id: str
    crew_name: str
    goal: str
    status: str
    progress_percentage: float
    current_node: str = None
    execution_time_seconds: float = None
    history: list[str] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    results: Dict[str, Any] = Field(default_factory=dict)
    error_messages: list[str] = Field(default_factory=list)

class WorkflowStatusResponse(BaseModel):
    active_workflows: Dict[str, Dict[str, Any]]

# ==============================================================================
#  ROADMAP STEP 2.3: Human-in-the-Loop API Models
# ==============================================================================

class HumanRequestResponse(BaseModel):
    """Response-Modell für eine aktive Human-Request."""
    mission_id: str
    agent_name: str
    question: str
    context: str = ""
    options: list[str] = Field(default_factory=list)
    urgency: str = "medium"
    created_at: str  # ISO timestamp

class HumanInputRequest(BaseModel):
    """Request-Modell für die menschliche Antwort."""
    mission_id: str = Field(..., description="ID der pausierten Mission")
    response: str = Field(..., description="Die menschliche Antwort")

class HumanInputResponse(BaseModel):
    """Response-Modell nach erfolgreichem Human-Input."""
    mission_id: str
    status: str = "resumed"
    message: str = "Mission wurde mit menschlicher Eingabe fortgesetzt"

class PausedMissionsResponse(BaseModel):
    """Response-Modell für die Liste pausierter Missionen."""
    paused_missions: list[HumanRequestResponse]
    total_count: int

# ==============================================================================
#  3. API-Endpunkte
# ==============================================================================

@app.get("/", summary="Health Check")
async def read_root():
    """Gibt den Status der Bridge-API zurück."""
    return {
        "status": "LLM2LLM-Bridge API is running.",
        "version": "1.0.0",
        "adapters": list(bridge.adapters.keys()) if bridge else []
    }


@app.get("/v1/models", response_model=AvailableModelsResponse, summary="Verfügbare Modelle abrufen")
async def get_available_models():
    """Gibt eine Liste aller verfügbaren LLM-Modelle zurück."""
    return {
        "models": bridge.get_available_models() if bridge else []
    }

@app.get("/v1/models/detailed", response_model=DetailedModelsResponse, summary="Detaillierte Modell-Informationen")
async def get_detailed_models():
    """Gibt detaillierte Informationen über alle Modelle aus dem Registry zurück."""
    if not bridge:
        raise HTTPException(status_code=500, detail="Bridge nicht initialisiert")
    
    # Lade das komplette Registry
    import yaml
    registry_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'models.yaml')
    
    try:
        with open(registry_path, 'r', encoding='utf-8') as f:
            registry_data = yaml.safe_load(f)
        
        # Separiere Modelle und Metadaten
        models = {k: v for k, v in registry_data.items() if not k.startswith('_')}
        registry_info = {k: v for k, v in registry_data.items() if k.startswith('_')}
        
        return DetailedModelsResponse(
            models=models,
            total_count=len(models),
            registry_info=registry_info
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Laden des Model Registry: {str(e)}")


@app.post("/v1/conversation", response_model=NewConversationResponse, summary="Neue Konversation starten")
async def start_new_conversation():
    """
    Erstellt eine neue, einzigartige Konversations-ID und gibt sie zurück.
    Dies ist der erste Schritt, um eine neue Konversation zu beginnen.
    """
    conv_id = f"conv_api_{uuid.uuid4().hex[:8]}"
    return {
        "message": "New conversation created successfully.",
        "conversation_id": conv_id
    }


@app.post("/v1/conversation/{conversation_id}/message", response_model=MessageResponse, summary="Nachricht in Konversation senden")
async def send_message(conversation_id: str, request: MessageRequest):
    """
    Sendet eine Nachricht an ein LLM innerhalb einer bestehenden Konversation.
    """
    if not bridge:
        raise HTTPException(status_code=500, detail="Bridge not initialized")
        
    try:
        response_text = await bridge.bridge_message(
            conversation_id=conversation_id,
            target_llm_name=request.target_llm,
            message=request.prompt
        )
        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "target_llm": request.target_llm
        }
    except CircuitBreakerError as e:
        # ▶️ Spezifische Fehlerbehandlung für einen offenen Circuit Breaker
        detail_msg = f"Der Dienst für '{request.target_llm}' ist vorübergehend nicht verfügbar. "
        if e.next_attempt_at:
            detail_msg += f"Nächster Versuch möglich ab: {e.next_attempt_at.isoformat()}"
        else:
            detail_msg += "Bitte versuchen Sie es später erneut."
        
        raise HTTPException(
            status_code=503,
            detail=detail_msg,
            headers={"Retry-After": "60"}  # Client soll es in 60 Sekunden erneut versuchen
        )
    except Exception as e:
        # Fängt alle Fehler aus der Bridge (Circuit Breaker, State Machine etc.)
        # und gibt einen sauberen HTTP-Fehler zurück.
        error_message = str(e)
        
        # Spezifische Fehlerbehandlung
        if "Invalid state transition" in error_message:
            raise HTTPException(status_code=400, detail=f"State Machine Error: {error_message}")
        elif "Circuit is open" in error_message:
            # Fallback für alte Circuit Breaker Exceptions
            raise HTTPException(status_code=503, detail=f"Service Unavailable: {error_message}")
        elif "Could not resolve target" in error_message:
            raise HTTPException(status_code=404, detail=f"Model Not Found: {error_message}")
        else:
            # Generischer Serverfehler
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=str(e))


# ==============================================================================
#  4. Workflow-Endpunkte
# ==============================================================================

@app.post("/v1/workflow/execute", response_model=WorkflowResponse, summary="Workflow ausführen")
async def execute_workflow(request: WorkflowRequest):
    """
    Führt einen definierten Workflow aus.
    
    Ein Workflow besteht aus mehreren Schritten, die sequenziell ausgeführt werden.
    Jeder Schritt kann auf die Ausgaben vorheriger Schritte zugreifen.
    """
    if not bridge or not orchestrator:
        raise HTTPException(status_code=500, detail="Bridge oder Orchestrator nicht initialisiert")
    
    try:
        # Workflow validieren
        validation_errors = WorkflowValidator.validate_workflow(request.workflow)
        if validation_errors:
            raise HTTPException(
                status_code=400, 
                detail=f"Workflow-Validierung fehlgeschlagen: {'; '.join(validation_errors)}"
            )
        
        # Workflow ausführen
        result = await orchestrator.execute_workflow(request.workflow)
        
        return WorkflowResponse(
            workflow_id=result['workflow_id'],
            workflow_name=result['workflow_name'],
            success=result['success'],
            duration=result['duration'],
            total_steps=result['total_steps'],
            completed_steps=result['completed_steps'],
            failed_steps=result['failed_steps'],
            outputs=result['outputs'],
            error=result.get('error')
        )
        
    except HTTPException:
        # HTTPExceptions durchreichen
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Workflow-Ausführung fehlgeschlagen: {str(e)}")


@app.post("/v1/workflow/execute-yaml", response_model=WorkflowResponse, summary="YAML-Workflow ausführen")
async def execute_yaml_workflow(yaml_content: str):
    """
    Führt einen Workflow aus, der als YAML-String definiert ist.
    
    Dies ist eine Convenience-Methode für die direkte Ausführung von YAML-Workflows.
    """
    if not bridge or not orchestrator:
        raise HTTPException(status_code=500, detail="Bridge oder Orchestrator nicht initialisiert")
    
    try:
        # YAML parsen
        workflow_def = yaml.safe_load(yaml_content)
        
        # Workflow validieren
        validation_errors = WorkflowValidator.validate_workflow(workflow_def)
        if validation_errors:
            raise HTTPException(
                status_code=400, 
                detail=f"YAML-Workflow-Validierung fehlgeschlagen: {'; '.join(validation_errors)}"
            )
        
        # Workflow ausführen
        result = await orchestrator.execute_workflow(workflow_def)
        
        return WorkflowResponse(
            workflow_id=result['workflow_id'],
            workflow_name=result['workflow_name'],
            success=result['success'],
            duration=result['duration'],
            total_steps=result['total_steps'],
            completed_steps=result['completed_steps'],
            failed_steps=result['failed_steps'],
            outputs=result['outputs'],
            error=result.get('error')
        )
        
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"YAML-Parsing-Fehler: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"YAML-Workflow-Ausführung fehlgeschlagen: {str(e)}")


@app.get("/v1/workflow/status", response_model=WorkflowStatusResponse, summary="Aktive Workflows anzeigen")
async def get_workflow_status():
    """
    Gibt Informationen über aktuell laufende Workflows zurück.
    """
    if not orchestrator:
        raise HTTPException(status_code=500, detail="Orchestrator nicht initialisiert")
    
    return WorkflowStatusResponse(
        active_workflows=orchestrator.get_active_workflows()
    )


# ==============================================================================
#  PHASE 5.2: Multi-Agent Mission Endpoints
# ==============================================================================

@app.post("/v1/mission/execute", response_model=MissionResponse, summary="Multi-Agenten Mission ausführen")
async def execute_mission(request: MissionRequest):
    """
    Führt eine Mission mit einem Multi-Agenten-Team aus.
    
    Die Mission wird von einem Supervisor geplant und dann von spezialisierten
    Agenten schrittweise ausgeführt. Die Kommunikation erfolgt über strukturierte
    Datenformate (Pydantic-Modelle).
    """
    if not agent_orchestrator:
        raise HTTPException(status_code=500, detail="Agent-Orchestrator nicht initialisiert")
    
    try:
        # Mission mit persistentem State-Tracking ausführen
        final_state = await agent_orchestrator.execute_mission(
            crew_name=request.crew_name,
            goal=request.goal,
            parameters=request.parameters,
            state_repository=state_repository  # Repository übergeben
        )
        
        # Response erstellen mit JSON-serialisierbaren Daten
        return MissionResponse(
            mission_id=final_state.mission_id,
            crew_name=final_state.crew_name,
            goal=final_state.high_level_goal,
            status=final_state.status,
            progress_percentage=final_state.progress_percentage,
            execution_time_seconds=final_state.execution_time_seconds,
            results=json_serializer(final_state.results),
            history=final_state.history,
            error_messages=final_state.error_messages
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Mission execution failed: {str(e)}")

@app.post("/v1/mission/execute-template", response_model=MissionResponse, summary="Template-basierte Mission ausführen")
async def execute_template_mission(request: TemplateMissionRequest):
    """
    Führt eine Mission basierend auf einem vordefinierten Template aus.
    
    Templates definieren standardisierte Mission-Typen mit Platzhaltern für Parameter.
    """
    if not agent_orchestrator:
        raise HTTPException(status_code=500, detail="Agent-Orchestrator nicht initialisiert")
    
    try:
        # Template-Mission mit persistentem State-Tracking ausführen
        # TODO: Implementiere execute_template_mission im AgentOrchestrator
        # Für jetzt verwenden wir execute_mission mit Template-Parametern
        if request.template_name not in registry_config.get('mission_templates', {}):
            raise HTTPException(status_code=400, detail=f"Template '{request.template_name}' nicht gefunden")
        
        template = registry_config['mission_templates'][request.template_name]
        crew_name = template.get('crew')
        goal = template.get('goal', 'Template-basierte Mission')
        
        final_state = await agent_orchestrator.execute_mission(
            crew_name=crew_name,
            goal=goal,
            parameters=request.parameters,
            state_repository=state_repository  # Repository übergeben
        )
        
        # Response erstellen mit JSON-serialisierbaren Daten
        return MissionResponse(
            mission_id=final_state.mission_id,
            crew_name=final_state.crew_name,
            goal=final_state.high_level_goal,
            status=final_state.status,
            progress_percentage=final_state.progress_percentage,
            execution_time_seconds=final_state.execution_time_seconds,
            results=json_serializer(final_state.results),
            history=final_state.history,
            error_messages=final_state.error_messages
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Template mission execution failed: {str(e)}")

@app.get("/v1/mission/crews", response_model=CrewListResponse, summary="Verfügbare Crews und Agenten auflisten")
async def list_crews():
    """
    Gibt eine Übersicht über alle verfügbaren Crews, Agenten und Templates zurück.
    """
    if not registry_config:
        raise HTTPException(status_code=500, detail="Registry nicht geladen")
    
    return CrewListResponse(
        crews=registry_config.get('crews', {}),
        agents=registry_config.get('agents', {}),
        templates=registry_config.get('mission_templates', {})
    )

@app.get("/v1/mission/{mission_id}/status", response_model=MissionStatusResponse, summary="Live-Status einer Mission abrufen")
async def get_mission_status(mission_id: str):
    """
    Gibt den aktuellen Status einer laufenden oder abgeschlossenen Mission zurück.
    
    Ermöglicht es dem Frontend, den Fortschritt einer Mission in Echtzeit zu verfolgen.
    """
    # ✅ Neue Logik: Repository verwenden
    if not state_repository:
        raise HTTPException(status_code=503, detail="State repository not available")
    
    state = await state_repository.get_by_id(mission_id)
    if not state:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' nicht gefunden oder abgelaufen")
    
    # Erstelle formatierte Ergebnisse für die Response
    formatted_results = {}
    for agent_name, result in state.results.items():
        if hasattr(result, 'model_dump'):
            formatted_results[agent_name] = result.model_dump()
        else:
            formatted_results[agent_name] = str(result)
    
    return MissionStatusResponse(
        mission_id=state.mission_id,
        crew_name=state.crew_name,
        goal=state.high_level_goal,
        status=state.status,
        progress_percentage=state.progress_percentage,
        current_node=state.current_node,
        execution_time_seconds=state.execution_time_seconds or 0.0,
        history=state.history,
        completed_nodes=state.completed_nodes,
        results=formatted_results,
        error_messages=state.error_messages
    )

@app.get("/v1/mission/active", summary="Alle aktiven Missionen anzeigen")
async def get_active_missions():
    """
    Gibt eine Liste aller aktuell laufenden Missionen zurück.
    """
    if not state_repository:
        raise HTTPException(status_code=503, detail="State repository not available")
    
    # Hole alle aktiven Mission-IDs und States
    active_ids = await state_repository.list_active_ids()
    active_list = []
    
    for mission_id in active_ids:
        state = await state_repository.get_by_id(mission_id)
        if state:  # Falls die Mission zwischenzeitlich gelöscht wurde
            active_list.append({
                "mission_id": mission_id,
                "crew_name": state.crew_name,
                "goal": state.high_level_goal[:100] + "..." if len(state.high_level_goal) > 100 else state.high_level_goal,
                "status": state.status,
                "progress_percentage": state.progress_percentage,
                "current_node": state.current_node
            })
    
    return {
        "active_missions": active_list,
        "total_count": len(active_list)
    }

# ==============================================================================
#  ROADMAP STEP 2.3: Human-in-the-Loop API Endpoints
# ==============================================================================

@app.get("/v1/human/requests", response_model=PausedMissionsResponse, summary="Alle Missionen abrufen, die auf menschliche Eingabe warten")
async def get_human_requests():
    """
    Gibt eine Liste aller Missionen zurück, die auf menschliche Eingabe warten.
    
    Diese Endpunkt ermöglicht es einem Dashboard oder Frontend, alle pausierten
    Missionen anzuzeigen, bei denen ein Agent menschliche Hilfe benötigt.
    """
    if not state_repository:
        raise HTTPException(status_code=503, detail="State repository not available")
    
    try:
        # Hole alle aktiven Mission-IDs
        active_ids = await state_repository.list_active_ids()
        paused_missions = []
        
        for mission_id in active_ids:
            state = await state_repository.get_by_id(mission_id)
            if state and state.status == "AWAITING_HUMAN_INPUT" and state.active_human_request:
                paused_missions.append(HumanRequestResponse(
                    mission_id=state.mission_id,
                    agent_name=state.active_human_request.agent_name,
                    question=state.active_human_request.question,
                    context=state.active_human_request.context,
                    options=state.active_human_request.options or [],
                    urgency=state.active_human_request.urgency,
                    created_at=state.active_human_request.created_at.isoformat()
                ))
        
        return PausedMissionsResponse(
            paused_missions=paused_missions,
            total_count=len(paused_missions)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen pausierter Missionen: {str(e)}")

@app.get("/v1/human/requests/{mission_id}", response_model=HumanRequestResponse, summary="Details einer spezifischen Human-Request abrufen")
async def get_human_request(mission_id: str):
    """
    Gibt die Details einer spezifischen Human-Request für eine pausierte Mission zurück.
    
    Args:
        mission_id: Die ID der pausierten Mission
        
    Returns:
        HumanRequestResponse mit den Details der Anfrage
    """
    if not state_repository:
        raise HTTPException(status_code=503, detail="State repository not available")
    
    try:
        state = await state_repository.get_by_id(mission_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' nicht gefunden")
        
        if state.status != "AWAITING_HUMAN_INPUT":
            raise HTTPException(status_code=400, detail=f"Mission '{mission_id}' wartet nicht auf menschliche Eingabe (Status: {state.status})")
        
        if not state.active_human_request:
            raise HTTPException(status_code=400, detail=f"Mission '{mission_id}' hat keine aktive Human-Request")
        
        return HumanRequestResponse(
            mission_id=state.mission_id,
            agent_name=state.active_human_request.agent_name,
            question=state.active_human_request.question,
            context=state.active_human_request.context,
            options=state.active_human_request.options or [],
            urgency=state.active_human_request.urgency,
            created_at=state.active_human_request.created_at.isoformat()
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Abrufen der Human-Request: {str(e)}")

@app.post("/v1/human/respond", response_model=HumanInputResponse, summary="Menschliche Antwort für eine pausierte Mission senden")
async def provide_human_response(request: HumanInputRequest):
    """
    Sendet eine menschliche Antwort für eine pausierte Mission und setzt die Mission fort.
    
    Args:
        request: HumanInputRequest mit mission_id und der menschlichen Antwort
        
    Returns:
        HumanInputResponse mit dem Status der fortgesetzten Mission
    """
    if not state_repository:
        raise HTTPException(status_code=503, detail="State repository not available")
    
    if not agent_orchestrator:
        raise HTTPException(status_code=503, detail="Agent orchestrator not available")
    
    try:
        # Hole und validiere die Mission
        state = await state_repository.get_by_id(request.mission_id)
        if not state:
            raise HTTPException(status_code=404, detail=f"Mission '{request.mission_id}' nicht gefunden")
        
        if state.status != "AWAITING_HUMAN_INPUT":
            raise HTTPException(status_code=400, detail=f"Mission '{request.mission_id}' wartet nicht auf menschliche Eingabe (Status: {state.status})")
        
        if not state.active_human_request:
            raise HTTPException(status_code=400, detail=f"Mission '{request.mission_id}' hat keine aktive Human-Request")
        
        # ▶️ Verwende die neue resume_mission-Methode des AgentOrchestrators
        updated_state = await agent_orchestrator.resume_mission(
            mission_id=request.mission_id,
            human_response=request.response,
            state_repository=state_repository
        )
        
        # Bestimme den Status der Response
        if updated_state.status == "AWAITING_HUMAN_INPUT":
            # Mission pausiert erneut
            status = "paused_again"
            message = f"Mission '{request.mission_id}' wurde fortgesetzt, aber pausiert erneut für weitere menschliche Eingabe"
        elif updated_state.status == "COMPLETED":
            status = "completed"
            message = f"Mission '{request.mission_id}' wurde mit menschlicher Eingabe fortgesetzt und erfolgreich abgeschlossen"
        elif updated_state.status == "ERROR":
            status = "error"
            message = f"Mission '{request.mission_id}' konnte nicht fortgesetzt werden (Fehler aufgetreten)"
        else:
            status = "resumed"
            message = f"Mission '{request.mission_id}' wurde mit menschlicher Eingabe fortgesetzt"
        
        return HumanInputResponse(
            mission_id=request.mission_id,
            status=status,
            message=message
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Fehler beim Verarbeiten der menschlichen Antwort: {str(e)}")

@app.get("/v1/plugins/status", summary="Plugin-Status anzeigen")
async def get_plugin_status():
    """
    Gibt Informationen über geladene Plugins und verfügbare Adapter zurück.
    """
    if not bridge:
        raise HTTPException(status_code=500, detail="Bridge nicht initialisiert")
    
    return bridge.get_plugin_status()

if __name__ == "__main__":
    import uvicorn
    
    try:
        print("🚀 [STARTUP] Starte LLM Bridge Server...")
        uvicorn.run(app, host="0.0.0.0", port=8000)
        
    except KeyboardInterrupt:
        print("🛑 [SHUTDOWN] Server durch Benutzer beendet")
    except Exception as e:
        print(f"❌ [ERROR] Unerwarteter Fehler: {e}")
        import sys
        sys.exit(1)
    finally:
        print("🏁 [CLEANUP] Server-Prozess vollständig beendet")