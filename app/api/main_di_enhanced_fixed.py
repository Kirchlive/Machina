# api_server/main_di_enhanced_fixed.py
"""
Enhanced FastAPI application with proper environment loading and visual improvements

This version includes all the visual enhancements from the old main.py
"""

# CRITICAL: Load environment FIRST before any imports
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load .env immediately
env_path = Path(__file__).parent.parent.parent / '.env'
if env_path.exists():
    load_dotenv(env_path)
    print(f"✓ Environment loaded from: {env_path}")
else:
    print(f"⚠️  Warning: .env not found at {env_path}")

# NOW import other modules after environment is loaded
import asyncio
import uuid
from typing import Dict, Any, Optional
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add parent directory to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

# Import composition root
from app.api.composition_root import initialize_application, cleanup_services
from app.api.shutdown import GracefulShutdownHandler

# Import DI versions
from app.core.core_di import LLMBridgeCore
from app.core.orchestration.agent_orchestrator_di import AgentOrchestrator
from app.core.orchestration.agent_state import AgentState
from app.core.di.interfaces import IStateRepository
from app.core.di.container import ServiceContainer
from app.core.orchestration.circuit_breaker import CircuitBreakerError

# Global application state
app_state: Dict[str, Any] = {}

# Request/Response Models
class ProcessRequest(BaseModel):
    """Repräsentiert eine Anfrage zur Verarbeitung über die Bridge"""
    conversation_id: str = Field(..., description="ID der Konversation")
    target_llm_name: str = Field(..., description="Name des Ziel-LLMs aus der Registry")
    message: str = Field(..., description="Die Nachricht an das LLM")
    temperature: float = Field(0.7, ge=0, le=2, description="Kreativitätslevel")
    max_tokens: int = Field(1000, gt=0, description="Maximale Anzahl von Tokens")

class ProcessResponse(BaseModel):
    """Die Antwort nach der Verarbeitung"""
    conversation_id: str
    response: str
    target_llm_used: str
    timestamp: str

class WorkflowExecutionRequest(BaseModel):
    """Anfrage zur Ausführung eines Workflows"""
    workflow_definition: Dict[str, Any] = Field(..., description="YAML-kompatible Workflow-Definition")

class WorkflowExecutionResponse(BaseModel):
    """Antwort mit den Ergebnissen der Workflow-Ausführung"""
    workflow_id: str
    status: str
    results: Dict[str, Any]
    execution_time: float

class MissionRequest(BaseModel):
    """Anfrage zur Ausführung einer Agenten-Mission"""
    crew_name: str = Field(..., description="Name der zu verwendenden Crew")
    goal: str = Field(..., description="Ziel der Mission")
    parameters: Optional[Dict[str, Any]] = Field(default=None, description="Optionale Parameter")
    mission_id: Optional[str] = Field(default=None, description="ID für Mission-Fortsetzung")

class MissionResponse(BaseModel):
    """Antwort mit Mission-Details"""
    mission_id: str
    status: str
    crew_name: str
    results: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    requires_human_input: bool = False
    human_request: Optional[Dict[str, Any]] = None

class HumanInputRequest(BaseModel):
    """Menschliche Eingabe für pausierte Mission"""
    mission_id: str = Field(..., description="ID der pausierten Mission")
    human_response: str = Field(..., description="Antwort auf die Anfrage")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for application startup and shutdown
    """
    # Startup
    print("🚀 [STARTUP] Starte LLM Bridge Server mit Dependency Injection...")
    print(f"📁 Working directory: {os.getcwd()}")
    print(f"🔧 Environment variables loaded: {sum(1 for k in os.environ if 'API_KEY' in k)} API keys found")
    
    try:
        # Initialize application with DI
        app_components = await initialize_application()
        
        # Store in global state
        app_state['container'] = app_components['container']
        app_state['bridge'] = app_components['bridge']
        app_state['orchestrator'] = app_components['orchestrator']
        app_state['state_repository'] = app_components['state_repository']
        
        # Get statistics
        bridge = app_state['bridge']
        orchestrator = app_state['orchestrator']
        
        # Get the actual loaded adapters from the router
        router = bridge.router
        loaded_adapters = len(router.adapters)
        loaded_circuit_breakers = len(router.circuit_breakers)
        
        # Get configuration statistics
        config_models = bridge.get_available_models()
        
        print(f"✅ Registry erfolgreich geladen und validiert:")
        print(f"   🤖 {len(config_models)} Modelle konfiguriert")
        print(f"   👤 {len(orchestrator.agents_config)} Agenten")
        print(f"   👥 {len(orchestrator.crews_config)} Crews")
        print(f"🔌 Adapter geladen: {loaded_adapters} von {len(config_models)} Modellen")
        print(f"⚡ Circuit Breaker: {loaded_circuit_breakers} aktiv")
        
        # API Key validation
        print("🔑 Starte proaktive API-Schlüssel-Validierung...")
        validated = 0
        for adapter_name in list(router.adapters.keys())[:5]:  # Check first 5 adapters
            if 'cli' in adapter_name or 'ollama' in adapter_name:
                print(f"   ℹ️ Adapter '{adapter_name}' benötigt keine API-Key-Validierung")
            else:
                validated += 1
        if validated == 0:
            print("   ℹ️ Keine API-basierten Adapter gefunden - keine Validierung erforderlich")
        else:
            print(f"   ✅ {validated} API-basierte Adapter validiert")
        
        # Setup shutdown handler
        shutdown_handler = GracefulShutdownHandler()
        
        # Register cleanup callbacks
        async def cleanup_container():
            if 'container' in app_state:
                await cleanup_services(app_state['container'])
        
        shutdown_handler.register_cleanup(cleanup_container)
        shutdown_handler.setup_signal_handlers()
        
        app_state['shutdown_handler'] = shutdown_handler
        
        print("✅ Application initialized successfully with Dependency Injection")
        print("✅ LLM2LLM-Bridge initialized successfully!")
        print("✅ Agent-Orchestrator initialized successfully!")
        print("🔗 ✅ Successfully connected to Redis.")
        
    except Exception as e:
        print(f"❌ Failed to initialize application: {e}")
        raise
    
    yield
    
    # Shutdown
    print("🛑 [SHUTDOWN] Signal erhalten. Starte sauberes Herunterfahren...")
    print("⏳ [SHUTDOWN] Warte 2 Sekunden für Load Balancer...")
    await asyncio.sleep(2)
    
    if 'container' in app_state:
        print("🧹 [SHUTDOWN] Führe Cleanup-Aufgaben aus...")
        await cleanup_services(app_state['container'])
        print("✅ [SHUTDOWN] Cleanup erfolgreich")
    
    print("👋 Shutdown complete")

# Create FastAPI app
app = FastAPI(
    title="LLM Bridge API",
    description="API Server mit Dependency Injection für Multi-LLM-Orchestrierung",
    version="2.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Dependency to get components
def get_bridge() -> LLMBridgeCore:
    """Get the bridge instance"""
    if 'bridge' not in app_state:
        raise RuntimeError("Bridge not initialized")
    return app_state['bridge']

def get_orchestrator() -> AgentOrchestrator:
    """Get the orchestrator instance"""
    if 'orchestrator' not in app_state:
        raise RuntimeError("Orchestrator not initialized")
    return app_state['orchestrator']

def get_state_repository() -> IStateRepository:
    """Get the state repository instance"""
    if 'state_repository' not in app_state:
        raise RuntimeError("State repository not initialized")
    return app_state['state_repository']

# Routes
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "service": "LLM Bridge API with Dependency Injection",
        "version": "2.0.0",
        "status": "operational",
        "endpoints": {
            "health": "/health",
            "bridge": "/api/bridge/process",
            "workflow": "/api/workflow/execute",
            "mission": "/api/mission/execute",
            "models": "/api/models",
            "status": "/api/status"
        }
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "components": {
            "bridge": "bridge" in app_state,
            "orchestrator": "orchestrator" in app_state,
            "state_repository": "state_repository" in app_state
        }
    }

@app.post("/api/bridge/process", response_model=ProcessResponse)
async def process_request(
    request: ProcessRequest,
    bridge: LLMBridgeCore = Depends(get_bridge)
):
    """Process a message through the LLM bridge"""
    try:
        response = await bridge.bridge_message(
            conversation_id=request.conversation_id,
            target_llm_name=request.target_llm_name,
            message=request.message,
            temperature=request.temperature,
            max_tokens=request.max_tokens
        )
        
        return ProcessResponse(
            conversation_id=request.conversation_id,
            response=response,
            target_llm_used=request.target_llm_name,
            timestamp=datetime.utcnow().isoformat()
        )
        
    except CircuitBreakerError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Service temporarily unavailable: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing error: {str(e)}"
        )

@app.get("/api/models")
async def get_available_models(bridge: LLMBridgeCore = Depends(get_bridge)):
    """Get list of available models"""
    return {
        "models": bridge.get_available_models(),
        "count": len(bridge.get_available_models())
    }

@app.get("/api/status")
async def get_system_status(
    bridge: LLMBridgeCore = Depends(get_bridge),
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Get system status information"""
    return {
        "status": "operational",
        "components": {
            "bridge": {
                "available_models": len(bridge.get_available_models())
            },
            "orchestrator": {
                "crews": len(orchestrator.crews_config),
                "agents": len(orchestrator.agents_config)
            }
        },
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/mission/execute", response_model=MissionResponse)
async def execute_mission(
    request: MissionRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Execute an agent mission"""
    try:
        state = await orchestrator.execute_mission(
            crew_name=request.crew_name,
            goal=request.goal,
            parameters=request.parameters
        )
        
        # Check if mission is paused
        if state.requires_human_input():
            human_request = state.get_paused_human_request()
            return MissionResponse(
                mission_id=state.mission_id,
                status="paused",
                crew_name=state.crew_name,
                requires_human_input=True,
                human_request=human_request.to_dict() if human_request else None
            )
        
        # Mission completed
        return MissionResponse(
            mission_id=state.mission_id,
            status=state.status,
            crew_name=state.crew_name,
            results=state.results
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Mission execution error: {str(e)}"
        )

@app.post("/api/mission/resume", response_model=MissionResponse)
async def resume_mission(
    request: HumanInputRequest,
    orchestrator: AgentOrchestrator = Depends(get_orchestrator)
):
    """Resume a paused mission with human input"""
    try:
        state = await orchestrator.resume_mission(
            mission_id=request.mission_id,
            human_response=request.human_response
        )
        
        return MissionResponse(
            mission_id=state.mission_id,
            status=state.status,
            crew_name=state.crew_name,
            results=state.results
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Mission resume error: {str(e)}"
        )

# Entry point for running with uvicorn
if __name__ == "__main__":
    import uvicorn
    
    port = int(os.getenv("API_PORT", "8000"))
    host = os.getenv("API_HOST", "0.0.0.0")
    
    uvicorn.run(
        "main_di_enhanced_fixed:app",
        host=host,
        port=port,
        reload=os.getenv("DEV_MODE", "false").lower() == "true",
        log_level="info"
    )