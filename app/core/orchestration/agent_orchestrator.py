# llm_bridge/orchestration/agent_orchestrator.py
"""
StateGraph Engine für die Orchestrierung von Multi-Agenten-Workflows.
Inspiriert von LangGraph und CrewAI-Patterns.
"""
import json
import yaml
import asyncio
from typing import Dict, Any, Optional, List
from datetime import datetime

from .agent_state import AgentState, StateManager
from .data_models import TaskPlan, ResearchReport, FinalReport, QAReport, HumanRequest, QualityAssessment
from ..core import LLMBridgeCore
from ..tools.registry import TOOL_REGISTRY, HumanInterventionRequired
from ..repositories.agent_state_repository import IAgentStateRepository
import logging

logger = logging.getLogger(__name__)

class AgentOrchestrator:
    """
    Hauptklasse für die Orchestrierung von Multi-Agenten-Workflows.
    Führt einen StateGraph aus und koordiniert die Zusammenarbeit zwischen Agenten.
    """
    
    def __init__(self, bridge: LLMBridgeCore, registry_config: Dict[str, Any]):
        self.bridge = bridge
        self.registry_config = registry_config
        self.crews_config = registry_config.get('crews', {})
        self.agents_config = registry_config.get('agents', {})
        self.mission_templates = registry_config.get('mission_templates', {})
        
        logger.info(f"AgentOrchestrator initialized with {len(self.crews_config)} crews and {len(self.agents_config)} agents")
    
    async def execute_mission(self, crew_name: str, goal: str, parameters: Optional[Dict[str, Any]] = None, state_repository: IAgentStateRepository = None) -> AgentState:
        """
        Führt eine vollständige Mission mit der angegebenen Crew aus.
        
        Args:
            crew_name: Name der zu verwendenden Crew aus registry.yaml
            goal: Hochrangiges Ziel der Mission
            parameters: Optionale Parameter für die Mission
            state_repository: Repository für persistente Zustandsspeicherung
            
        Returns:
            AgentState: Finaler Zustand nach Ausführung
        """
        # Validierung
        if crew_name not in self.crews_config:
            raise ValueError(f"Crew '{crew_name}' nicht in Registry gefunden")
        
        if not state_repository:
            raise ValueError("A state_repository must be provided to execute a mission.")
            
        crew_config = self.crews_config[crew_name]
        state = StateManager.create_mission_state(crew_name, goal)
        state.add_history_entry(f"Mission '{state.mission_id}' created.")
        await state_repository.save(state)  # ▶️ Initialen Zustand sofort speichern
        
        try:
            logger.info(f"Starting mission {state.mission_id} with crew {crew_name}")
            
            # Phase 1: Planung mit Supervisor
            await self._planning_phase(state, crew_config, parameters)
            await state_repository.save(state)  # ▶️ Zustand nach Planung speichern
            
            # Phase 2: Ausführung des State Graphs
            await self._execution_phase(state, crew_config, state_repository)
            
            # Phase 3: Finale Synthese
            await self._synthesis_phase(state, crew_config)
            await state_repository.save(state)  # ▶️ Zustand nach Synthese speichern
            
            state.complete_execution()
            await state_repository.save(state)  # ▶️ Finalen Zustand speichern
            logger.info(f"Mission {state.mission_id} completed successfully")
            
        except HumanInterventionRequired as e:
            # ▶️ Schritt 2.5: MISSION-LEVEL PAUSIERUNG - Mission elegant pausieren
            logger.info(f"🚦 Mission {state.mission_id} pausiert: Agent {e.request_details.agent_name} benötigt menschliche Eingabe")
            
            # Speichere den pausierten Zustand
            await state_repository.save(state)
            
            # Gib den pausierten Zustand zurück (nicht raise) - der Caller entscheidet über Fortsetzung
            return state
            
        except Exception as e:
            error_msg = f"Mission execution failed: {str(e)}"
            logger.error(error_msg)
            state.mark_error(error_msg)
            await state_repository.save(state)  # ▶️ Fehlerzustand speichern
            raise
        
        return state
    
    async def resume_mission(self, mission_id: str, human_response: str, state_repository: IAgentStateRepository) -> AgentState:
        """
        ▶️ SCHRITT 3: FORTSETZEN-LOGIK - Setzt eine pausierte Mission mit menschlicher Eingabe fort.
        
        Args:
            mission_id: ID der pausierten Mission
            human_response: Die menschliche Antwort auf die Anfrage
            state_repository: Repository für persistente Zustandsspeicherung
            
        Returns:
            AgentState: Aktualisierter Zustand nach Fortsetzung oder kompletter Beendigung
        """
        if not state_repository:
            raise ValueError("A state_repository must be provided to resume a mission.")
        
        # Lade den pausierten Zustand
        state = await state_repository.get_by_id(mission_id)
        if not state:
            raise ValueError(f"Mission '{mission_id}' nicht gefunden")
        
        if state.status != "AWAITING_HUMAN_INPUT":
            raise ValueError(f"Mission '{mission_id}' wartet nicht auf menschliche Eingabe (Status: {state.status})")
        
        if not state.active_human_request:
            raise ValueError(f"Mission '{mission_id}' hat keine aktive Human-Request")
        
        try:
            logger.info(f"🔄 Resuming mission {mission_id} with human response")
            
            # Speichere die menschliche Antwort in den Tools-Results
            requesting_agent = state.active_human_request.agent_name
            tool_result = {
                "status": "human_input_received",
                "response": human_response,
                "timestamp": datetime.now().isoformat(),
                "original_question": state.active_human_request.question
            }
            
            # Speichere das Tool-Ergebnis
            state.store_result(requesting_agent, tool_result, "human_response")
            
            # Setze Status zurück und entferne Human-Request
            state.status = "RUNNING"
            state.active_human_request = None
            state.add_history_entry(f"🤝 Mission resumed with human response: {human_response[:100]}...")
            
            # Speichere den aktualisierten Zustand
            await state_repository.save(state)
            
            # Hole die Crew-Konfiguration um fortzusetzen
            crew_name = state.crew_name
            if crew_name not in self.crews_config:
                raise ValueError(f"Crew '{crew_name}' nicht in Registry gefunden")
            
            crew_config = self.crews_config[crew_name]
            
            # ▶️ Setze die Ausführung vom aktuellen Knoten fort
            # Der Agent, der die Human-Request gestellt hat, sollte jetzt das Tool-Ergebnis verarbeiten können
            try:
                # Erstelle einen neuen Prompt mit der menschlichen Antwort für den wartenden Agenten
                await self._continue_agent_with_human_response(state, requesting_agent, human_response)
                
                # Speichere nach Agent-Fortsetzung
                await state_repository.save(state)
                
                # Setze die normale Ausführung fort
                await self._execution_phase(state, crew_config, state_repository)
                
                # Phase 3: Finale Synthese (falls noch nicht abgeschlossen)
                if state.status == "RUNNING":
                    await self._synthesis_phase(state, crew_config)
                    await state_repository.save(state)
                    
                    state.complete_execution()
                    await state_repository.save(state)
                
                logger.info(f"Mission {mission_id} resumed and completed successfully")
                
            except HumanInterventionRequired as e:
                # Mission pausiert erneut - das ist völlig normal
                logger.info(f"Mission {mission_id} pausiert erneut: {e.request_details.agent_name} benötigt weitere menschliche Eingabe")
                await state_repository.save(state)
                return state
                
        except Exception as e:
            error_msg = f"Mission resume failed: {str(e)}"
            logger.error(error_msg)
            state.mark_error(error_msg)
            await state_repository.save(state)
            raise
        
        return state
    
    async def _continue_agent_with_human_response(self, state: AgentState, agent_name: str, human_response: str):
        """
        Setzt einen spezifischen Agenten mit der menschlichen Antwort fort.
        
        Args:
            state: Mission-Zustand
            agent_name: Name des Agenten, der die Human-Request gestellt hat
            human_response: Die menschliche Antwort
        """
        if agent_name not in self.agents_config:
            raise ValueError(f"Agent '{agent_name}' nicht in Registry gefunden")
        
        agent_config = self.agents_config[agent_name]
        
        # Erstelle einen Fortsetzungs-Prompt mit der menschlichen Antwort
        continuation_prompt = self._create_continuation_prompt(agent_config, state, human_response)
        
        try:
            state.add_history_entry(f"Continuing agent {agent_name} with human response")
            logger.info(f"Continuing agent {agent_name} for mission {state.mission_id}")
            
            # Führe den Agenten mit der menschlichen Antwort fort
            final_response = await self._execute_agent_with_tools(
                state, agent_name, agent_config, continuation_prompt
            )
            
            # Strukturiere Ergebnis basierend auf Output Schema
            structured_result = self._structure_agent_result(final_response, agent_config)
            state.store_result(agent_name, structured_result, "output")
            
            # Speichere auch Raw Response
            state.store_result(agent_name, final_response, "raw")
            
            state.add_history_entry(f"Agent {agent_name} continued successfully with human input")
            
        except HumanInterventionRequired as e:
            # Agent benötigt erneut menschliche Eingabe - das ist erlaubt
            logger.info(f"Agent {agent_name} benötigt erneut menschliche Eingabe")
            raise e
            
        except Exception as e:
            error_msg = f"Agent {agent_name} continuation failed: {str(e)}"
            logger.error(error_msg)
            state.add_history_entry(error_msg)
            raise
    
    def _create_continuation_prompt(self, agent_config: Dict[str, Any], state: AgentState, human_response: str) -> str:
        """
        Erstellt einen Fortsetzungs-Prompt für einen Agenten mit der menschlichen Antwort.
        
        Args:
            agent_config: Agent-Konfiguration
            state: Mission-Zustand
            human_response: Die menschliche Antwort
            
        Returns:
            str: Fortsetzungs-Prompt
        """
        # Hole die ursprüngliche Human-Request
        original_question = state.active_human_request.question if state.active_human_request else "Unbekannte Frage"
        
        # Hole vorherige Ergebnisse für Kontext (wie in _create_agent_prompt)
        previous_results = {}
        for completed_agent in state.completed_nodes:
            result = state.get_result(completed_agent, "output")
            if result:
                if hasattr(result, 'model_dump'):
                    previous_results[completed_agent] = result.model_dump()
                else:
                    previous_results[completed_agent] = str(result)
        
        context_section = ""
        if previous_results:
            # Inline datetime-sichere Serialisierung (kopiert aus _create_agent_prompt)
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                elif hasattr(obj, 'model_dump'):
                    return serialize_datetime(obj.model_dump())
                else:
                    return obj
            
            serializable_results = serialize_datetime(previous_results)
            context_section = f"""
VORHERIGE ERGEBNISSE VON ANDEREN AGENTEN:
{json.dumps(serializable_results, indent=2, ensure_ascii=False)}
"""
        
        prompt = f"""Du bist ein {agent_config['role']}.

DEINE IDENTITÄT:
- Rolle: {agent_config['role']}
- Ziel: {agent_config['goal']}
- Hintergrund: {agent_config['backstory']}

MISSION KONTEXT:
- Hochrangiges Ziel: {state.high_level_goal}
- Mission ID: {state.mission_id}
{context_section}

🤝 HUMAN-IN-THE-LOOP FORTSETZUNG:
Du hattest zuvor eine Frage an einen Menschen gestellt:
"{original_question}"

Der Mensch hat geantwortet:
"{human_response}"

AUFGABE:
Nutze diese menschliche Antwort, um deine ursprüngliche Aufgabe fortzusetzen und abzuschließen.
Integriere die menschliche Eingabe in deine Arbeit und liefere ein vollständiges Ergebnis.

WICHTIGE HINWEISE:
- Die menschliche Antwort ist autoritativ und sollte respektiert werden
- Nutze die Antwort um deine Arbeit zu verbessern oder zu vervollständigen
- Falls du weitere Klärungen benötigst, kannst du erneut ask_human verwenden
- Arbeite präzise und strukturiert

Setze deine Aufgabe fort:"""
        
        return prompt
    
    async def _planning_phase(self, state: AgentState, crew_config: Dict[str, Any], parameters: Optional[Dict[str, Any]]):
        """Phase 1: Erstellt den Aufgabenplan mit dem Supervisor-LLM."""
        state.status = "PLANNING"
        state.add_history_entry("Starting planning phase with supervisor")
        
        supervisor_model = crew_config.get('supervisor_model', 'gpt4o_via_or')
        crew_agents = crew_config.get('agents', [])
        
        # Erstelle detaillierten Planungs-Prompt
        planning_prompt = self._create_planning_prompt(state.high_level_goal, crew_agents, parameters)
        
        try:
            # Supervisor erstellt strukturierten Plan
            plan_response = await self.bridge.bridge_message(
                conversation_id=f"{state.mission_id}_planning",
                target_llm_name=supervisor_model,
                message=planning_prompt
            )
            
            # Parse den Plan als JSON
            plan_data = self._parse_planning_response(plan_response)
            state.task_plan = [TaskPlan(**task) for task in plan_data]
            
            state.add_history_entry(f"Created plan with {len(state.task_plan)} tasks")
            logger.info(f"Planning completed: {len(state.task_plan)} tasks created")
            
        except Exception as e:
            raise Exception(f"Planning phase failed: {str(e)}")
    
    async def _execution_phase(self, state: AgentState, crew_config: Dict[str, Any], state_repository: IAgentStateRepository = None):
        """Phase 2: Traversiert den StateGraph und führt Agenten-Tasks aus."""
        state.start_execution()
        graph = crew_config.get('graph', {})
        
        # ADVANCED LAYER: Tracking für Feedback Loops
        iteration_count = 0
        max_iterations = crew_config.get('max_iterations', 3)
        
        # Starte beim Entry Point
        current_node = graph.get('entry_point')
        nodes_config = graph.get('nodes', {})
        
        while current_node and current_node != "END":
            state.set_current_node(current_node)
            
            # ADVANCED LAYER: Prüfe Iterationslimit
            if iteration_count >= max_iterations:
                state.add_history_entry(f"Maximum iterations ({max_iterations}) reached. Forcing completion.")
                logger.warning(f"Mission {state.mission_id} reached max iterations")
                break
            
            try:
                # Führe den aktuellen Agenten aus
                await self._execute_agent(state, current_node)
                
                # ▶️ Zustand nach jedem Agenten speichern
                if state_repository:
                    await state_repository.save(state)
                    
            except HumanInterventionRequired as e:
                # ▶️ Schritt 2.4: HAUPTPAUSIERUNG - Mission vollständig pausieren
                logger.info(f"🚦 Mission {state.mission_id} pausiert - warte auf menschliche Eingabe")
                
                # Stelle sicher, dass der Zustand gespeichert wird
                if state_repository:
                    await state_repository.save(state)
                
                # Exception nach oben weiterreichen zur Mission-Ebene
                raise e
            
            # ADVANCED LAYER: Prüfe Qualitätsschwelle bei QA-Agenten
            if 'qa' in current_node.lower():
                if await self._check_quality_threshold(state, crew_config):
                    state.add_history_entry("Quality threshold reached. Mission completed.")
                    break
            
            # INTELLIGENCE LAYER: Bestimme nächsten Knoten mit Conditional Transitions
            node_config = nodes_config.get(current_node, {})
            
            if "conditional_transitions" in node_config:
                # ADVANCED LAYER: Enhanced Conditional Transitions mit Feedback-Tracking
                current_node = await self._handle_conditional_transitions(
                    state, current_node, node_config['conditional_transitions'], crew_config
                )
                logger.info(f"Conditional transition: Next node is '{current_node}'")
                
                # Zähle Iteration bei Loop-back
                if current_node in state.completed_nodes:
                    iteration_count += 1
                    state.add_history_entry(f"Feedback loop iteration {iteration_count}: returning to {current_node}")
            else:
                # Standard transition
                current_node = node_config.get('transitions_to')
            
            # Kurze Pause zwischen Agenten
            await asyncio.sleep(0.5)
        
        state.add_history_entry("Execution phase completed")
    
    async def _execute_agent(self, state: AgentState, agent_name: str):
        """Führt einen spezifischen Agenten aus."""
        if agent_name not in self.agents_config:
            raise ValueError(f"Agent '{agent_name}' nicht in Registry gefunden")
        
        agent_config = self.agents_config[agent_name]
        
        # Finde passende Aufgabe für diesen Agenten
        task = self._find_task_for_agent(state, agent_name)
        if not task:
            state.add_history_entry(f"No specific task found for {agent_name}, using general assignment")
            task_description = f"Perform your role as {agent_config['role']} for the goal: {state.high_level_goal}"
        else:
            task_description = task.description
        
        # Erstelle Agent-Prompt
        agent_prompt = self._create_agent_prompt(agent_config, task_description, state)
        
        try:
            state.add_history_entry(f"Executing agent: {agent_name}")
            logger.info(f"Executing agent {agent_name} for mission {state.mission_id}")
            
            # INTELLIGENCE LAYER: Tool-Calling Integration
            final_response = await self._execute_agent_with_tools(
                state, agent_name, agent_config, agent_prompt
            )
            
            # Strukturiere Ergebnis basierend auf Output Schema
            structured_result = self._structure_agent_result(final_response, agent_config)
            state.store_result(agent_name, structured_result, "output")
            
            # Speichere auch Raw Response
            state.store_result(agent_name, final_response, "raw")
            
            state.add_history_entry(f"Agent {agent_name} completed successfully")
            
        except HumanInterventionRequired as e:
            # ▶️ Schritt 2.3: Human-in-the-Loop Exception auf Agent-Ebene behandeln
            logger.info(f"🚦 Agent {agent_name} benötigt menschliche Eingabe - Mission wird pausiert")
            
            # Exception nach oben weiterreichen, damit die Ausführungsphase pausiert
            raise e
            
        except Exception as e:
            error_msg = f"Agent {agent_name} execution failed: {str(e)}"
            logger.error(error_msg)
            state.add_history_entry(error_msg)
            raise
    
    async def _execute_agent_with_tools(self, 
                                       state: AgentState, 
                                       agent_name: str, 
                                       agent_config: Dict[str, Any], 
                                       initial_prompt: str) -> str:
        """
        INTELLIGENCE LAYER: Führt einen Agenten mit Tool-Calling-Unterstützung aus.
        
        Args:
            state: Mission-Zustand
            agent_name: Name des Agenten
            agent_config: Agent-Konfiguration aus registry.yaml
            initial_prompt: Ursprünglicher Agent-Prompt
            
        Returns:
            str: Finale Antwort des Agenten
        """
        # Hole verfügbare Tools für diesen Agenten
        agent_tools = agent_config.get('tools', [])
        
        # Wenn keine Tools verfügbar, führe den Agenten normal aus
        if not agent_tools:
            return await self.bridge.bridge_message(
                conversation_id=f"{state.mission_id}_{agent_name}",
                target_llm_name=agent_config['model'],
                message=initial_prompt
            )
        
        # Erweitere den Prompt um Tool-Informationen
        enhanced_prompt = self._create_tool_enhanced_prompt(initial_prompt, agent_tools)
        
        # Tool-Use-Schleife
        current_prompt = enhanced_prompt
        tool_call_count = 0
        max_tool_calls = 5  # Verhindere Endlosschleifen
        
        while tool_call_count < max_tool_calls:
            # Agent-Antwort erhalten
            llm_response = await self.bridge.bridge_message(
                conversation_id=f"{state.mission_id}_{agent_name}_tool_{tool_call_count}",
                target_llm_name=agent_config['model'],
                message=current_prompt
            )
            
            # Prüfe ob es sich um einen Tool-Call handelt
            if self._is_tool_call(llm_response):
                tool_call_count += 1
                
                # Parse und führe Tool aus
                tool_result = await self._execute_tool_call(llm_response, state, agent_name)
                
                # Erstelle neuen Prompt mit Tool-Ergebnis
                current_prompt = self._create_tool_result_prompt(
                    initial_prompt, llm_response, tool_result, agent_tools
                )
                
                # Logge Tool-Nutzung
                state.add_history_entry(f"Agent {agent_name} used tool, iteration {tool_call_count}")
                
            else:
                # Keine weiteren Tool-Calls, gib finale Antwort zurück
                state.add_history_entry(f"Agent {agent_name} completed after {tool_call_count} tool calls")
                return llm_response
        
        # Fallback: Maximale Tool-Calls erreicht
        state.add_history_entry(f"Agent {agent_name} reached max tool calls ({max_tool_calls})")
        logger.warning(f"Agent {agent_name} reached maximum tool calls")
        
        # Bitte den Agenten um eine finale Antwort ohne weitere Tools
        final_prompt = f"{initial_prompt}\n\nBitte gib deine finale Antwort basierend auf den bisher gesammelten Informationen. Verwende KEINE Tools mehr."
        
        return await self.bridge.bridge_message(
            conversation_id=f"{state.mission_id}_{agent_name}_final",
            target_llm_name=agent_config['model'],
            message=final_prompt
        )
    
    def _create_tool_enhanced_prompt(self, original_prompt: str, agent_tools: List[str]) -> str:
        """Erweitert den Agent-Prompt um Tool-Informationen."""
        
        # Sammle Tool-Informationen
        available_tools = {}
        for tool_name in agent_tools:
            if tool_name in TOOL_REGISTRY:
                tool_info = TOOL_REGISTRY[tool_name]
                available_tools[tool_name] = {
                    "description": tool_info['description'],
                    "parameters": tool_info['parameters']
                }
        
        if not available_tools:
            return original_prompt
        
        tools_json = json.dumps(available_tools, indent=2, ensure_ascii=False)
        
        enhanced_prompt = f"""{original_prompt}

VERFÜGBARE TOOLS:
{tools_json}

TOOL-NUTZUNG:
Du kannst jederzeit Tools verwenden, um zusätzliche Informationen zu sammeln oder Aufgaben auszuführen.
Um ein Tool zu nutzen, antworte mit einem JSON-Objekt im exakten Format:
{{"tool_name": "tool_name_hier", "args": {{"parameter1": "wert1", "parameter2": "wert2"}}}}

Nach der Tool-Ausführung erhältst du das Ergebnis und kannst dann weiterarbeiten.
Wenn du keine weiteren Tools benötigst, gib deine finale Antwort im normalen Textformat."""
        
        return enhanced_prompt
    
    def _is_tool_call(self, response: str) -> bool:
        """Prüft ob eine Agent-Antwort ein Tool-Call ist."""
        response = response.strip()
        
        # Einfache Heuristik: Beginnt mit { und enthält "tool_name"
        if response.startswith('{') and 'tool_name' in response:
            try:
                parsed = json.loads(response)
                return isinstance(parsed, dict) and 'tool_name' in parsed and 'args' in parsed
            except json.JSONDecodeError:
                return False
        
        return False
    
    async def _execute_tool_call(self, tool_call_response: str, state: AgentState, agent_name: str) -> Dict[str, Any]:
        """Führt einen Tool-Call aus und gibt das Ergebnis zurück."""
        try:
            tool_call = json.loads(tool_call_response.strip())
            tool_name = tool_call['tool_name']
            tool_args = tool_call.get('args', {})
            
            if tool_name not in TOOL_REGISTRY:
                return {
                    "error": f"Tool '{tool_name}' not found in registry",
                    "available_tools": list(TOOL_REGISTRY.keys())
                }
            
            tool_info = TOOL_REGISTRY[tool_name]
            tool_function = tool_info['function']
            
            # Logge Tool-Aufruf
            state.add_history_entry(f"Agent {agent_name} calling tool: {tool_name} with args: {tool_args}")
            logger.info(f"Executing tool {tool_name} for agent {agent_name}")
            
            # ▶️ Schritt 2.1: Setze agent_name in HumanRequest für bessere Kontextualisierung
            if tool_name == "ask_human" and "agent_name" not in tool_args:
                tool_args["agent_name"] = agent_name
            
            # ADVANCED LAYER: Führe Tool aus mit Human-in-the-Loop Support
            if tool_info.get('async', False):
                result = await tool_function(**tool_args)
            else:
                result = tool_function(**tool_args)
            
            state.add_history_entry(f"Tool {tool_name} completed successfully")
            return result
            
        except HumanInterventionRequired as e:
            # ▶️ Schritt 2.2: PAUSIEREN-LOGIK - Mission pausieren und Signal weiterreichen
            logger.info(f"🚦 Human intervention required for mission {state.mission_id}, agent {agent_name}")
            
            # Ergänze agent_name falls nicht gesetzt
            if not e.request_details.agent_name or e.request_details.agent_name == "unknown":
                e.request_details.agent_name = agent_name
            
            # Setze Mission-Status auf AWAITING_HUMAN_INPUT
            state.status = "AWAITING_HUMAN_INPUT"
            state.active_human_request = e.request_details
            
            # Logge die Pausierung
            state.add_history_entry(f"🚦 Mission pausiert: {agent_name} benötigt menschliche Eingabe")
            state.add_history_entry(f"📋 Frage: {e.request_details.question}")
            
            # Re-raise die Exception, damit sie bis zur Mission-Ebene propagiert
            raise e
            
        except json.JSONDecodeError as e:
            return {"error": f"Invalid JSON in tool call: {str(e)}"}
        except Exception as e:
            error_msg = f"Tool execution failed: {str(e)}"
            state.add_history_entry(f"Tool error: {error_msg}")
            logger.error(f"Tool execution error: {e}")
            return {"error": error_msg}
    
    def _create_tool_result_prompt(self, 
                                  original_prompt: str, 
                                  tool_call: str, 
                                  tool_result: Dict[str, Any], 
                                  available_tools: List[str]) -> str:
        """Erstellt einen neuen Prompt mit Tool-Ergebnis."""
        
        result_summary = json.dumps(tool_result, indent=2, ensure_ascii=False)[:1000]
        if len(json.dumps(tool_result)) > 1000:
            result_summary += "... (gekürzt)"
        
        return f"""{original_prompt}

TOOL-AUSFÜHRUNG:
Du hast das Tool verwendet: {tool_call}

TOOL-ERGEBNIS:
{result_summary}

Nutze diese Informationen um deine Aufgabe fortzusetzen. Du kannst weitere Tools verwenden oder deine finale Antwort geben.

VERFÜGBARE TOOLS: {', '.join(available_tools)}"""
    
    async def _synthesis_phase(self, state: AgentState, crew_config: Dict[str, Any]):
        """Phase 3: Supervisor fasst alle Ergebnisse zusammen."""
        state.add_history_entry("Starting synthesis phase")
        supervisor_model = crew_config.get('supervisor_model', 'gpt4o_via_or')
        
        # Sammle alle Ergebnisse
        all_results = {}
        for agent_name in state.completed_nodes:
            result = state.get_result(agent_name, "output")
            if result:
                all_results[agent_name] = result
        
        # Erstelle Synthese-Prompt
        synthesis_prompt = self._create_synthesis_prompt(state.high_level_goal, all_results)
        
        try:
            # Supervisor erstellt finale Synthese
            final_synthesis = await self.bridge.bridge_message(
                conversation_id=f"{state.mission_id}_synthesis",
                target_llm_name=supervisor_model,
                message=synthesis_prompt
            )
            
            state.store_result("supervisor", final_synthesis, "final_synthesis")
            state.add_history_entry("Synthesis phase completed")
            
        except Exception as e:
            logger.error(f"Synthesis phase failed: {str(e)}")
            state.add_history_entry(f"Synthesis failed: {str(e)}")
    
    def _create_planning_prompt(self, goal: str, agents: List[str], parameters: Optional[Dict[str, Any]]) -> str:
        """Erstellt den Prompt für die Planungsphase."""
        agents_info = []
        for agent_name in agents:
            if agent_name in self.agents_config:
                config = self.agents_config[agent_name]
                agents_info.append(f"- {agent_name}: {config['role']} - {config['goal']}")
        
        prompt = f"""Du bist ein Supervisor für ein Multi-Agenten-Team. Deine Aufgabe ist es, einen detaillierten Aufgabenplan zu erstellen.

ZIEL: {goal}

VERFÜGBARE AGENTEN:
{chr(10).join(agents_info)}

ZUSÄTZLICHE PARAMETER: {json.dumps(parameters or {}, indent=2)}

Erstelle einen strukturierten Plan als JSON-Array. Jede Aufgabe sollte folgende Struktur haben:
{{
  "task_id": "eindeutige_id",
  "description": "detaillierte_beschreibung",
  "assigned_agent": "agent_name",
  "expected_output": "erwarteter_output_typ",
  "priority": 1
}}

Antworte NUR mit dem JSON-Array, ohne zusätzlichen Text."""
        
        return prompt
    
    def _create_agent_prompt(self, agent_config: Dict[str, Any], task_description: str, state: AgentState) -> str:
        """Erstellt den Prompt für einen spezifischen Agenten."""
        # Hole vorherige Ergebnisse für Kontext
        previous_results = {}
        for completed_agent in state.completed_nodes:
            result = state.get_result(completed_agent, "output")
            if result:
                if hasattr(result, 'model_dump'):
                    previous_results[completed_agent] = result.model_dump()
                else:
                    previous_results[completed_agent] = str(result)
        
        context_section = ""
        if previous_results:
            # Inline datetime-sichere Serialisierung
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                elif isinstance(obj, dict):
                    return {k: serialize_datetime(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [serialize_datetime(item) for item in obj]
                elif hasattr(obj, 'model_dump'):
                    return serialize_datetime(obj.model_dump())
                else:
                    return obj
            
            serializable_results = serialize_datetime(previous_results)
            context_section = f"""
VORHERIGE ERGEBNISSE VON ANDEREN AGENTEN:
{json.dumps(serializable_results, indent=2, ensure_ascii=False)}
"""
        
        output_schema_name = agent_config.get('output_schema', 'Text')
        input_schema = agent_config.get('input_schema')
        
        # ▶️ Schritt 2.1: Spezifische Anweisungen für das QualityAssessment-Schema
        if output_schema_name == 'QualityAssessment':
            # Holen Sie sich das JSON-Schema aus dem Pydantic-Modell
            schema_json = QualityAssessment.model_json_schema()
            
            schema_instruction = f"""
WICHTIG: Dein Output MUSS ein gültiges JSON-Objekt sein, das dem folgenden Schema entspricht.
Gib NUR das JSON-Objekt zurück und sonst nichts. Keinen einleitenden Text, keine Erklärungen danach.

JSON Schema für deine Antwort:
```json
{json.dumps(schema_json, indent=2, ensure_ascii=False)}
```

BEISPIEL einer gültigen Antwort:
```json
{{
  "recommendation": "publish",
  "reasoning": "Der Artikel ist gut strukturiert und vollständig recherchiert.",
  "strengths": ["Klare Argumentation", "Gute Quellen"],
  "issues_found": [],
  "confidence_score": 0.9
}}
```

Verwende für 'recommendation' NUR diese Werte: "publish", "revise", "research_more", "fail"
"""
        else:
            # Fallback für andere/textbasierte Schemata
            schema_instruction = f"""
ERWARTETES OUTPUT-FORMAT: {output_schema_name}
"""
            if input_schema:
                schema_instruction += f"ERWARTETER INPUT-TYP: {input_schema}\n"
        
        prompt = f"""Du bist ein {agent_config['role']}.

DEINE IDENTITÄT:
- Rolle: {agent_config['role']}
- Ziel: {agent_config['goal']}
- Hintergrund: {agent_config['backstory']}

AKTUELLE AUFGABE:
{task_description}

MISSION KONTEXT:
- Hochrangiges Ziel: {state.high_level_goal}
- Mission ID: {state.mission_id}
{context_section}
{schema_instruction}

WICHTIGE HINWEISE:
- Arbeite präzise und strukturiert
- Nutze die vorherigen Ergebnisse anderer Agenten als Kontext
- Liefere ein Ergebnis, das dem erwarteten Format entspricht
- Sei gründlich aber effizient

Führe deine Aufgabe aus:"""
        
        return prompt
    
    def _create_synthesis_prompt(self, goal: str, results: Dict[str, Any]) -> str:
        """Erstellt den Prompt für die finale Synthese."""
        results_summary = {}
        for agent, result in results.items():
            if hasattr(result, 'model_dump'):
                results_summary[agent] = result.model_dump()
            else:
                results_summary[agent] = str(result)
        
        prompt = f"""Du bist ein Supervisor, der eine finale Synthese erstellt.

URSPRÜNGLICHES ZIEL: {goal}

GESAMMELTE ERGEBNISSE DER AGENTEN:
{json.dumps(results_summary, indent=2, ensure_ascii=False, default=str)}

AUFGABE:
Erstelle eine kohärente, finale Zusammenfassung, die:
1. Das ursprüngliche Ziel vollständig erfüllt
2. Alle wichtigen Erkenntnisse der Agenten integriert
3. Professionell und gut strukturiert ist
4. Einen klaren Mehrwert bietet

Liefere das finale Ergebnis:"""
        
        return prompt
    
    def _parse_planning_response(self, response: str) -> List[Dict[str, Any]]:
        """Parsed die JSON-Response des Planungs-LLM."""
        try:
            # Entferne mögliche Markdown-Formatierung
            if '```json' in response:
                response = response.split('```json')[1].split('```')[0]
            elif '```' in response:
                response = response.split('```')[1].split('```')[0]
            
            return json.loads(response.strip())
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse planning response: {response}")
            # Fallback: Erstelle einfachen Plan
            return [
                {
                    "task_id": "fallback_task_1",
                    "description": "Perform research and analysis",
                    "assigned_agent": "researcher",
                    "expected_output": "ResearchReport",
                    "priority": 1
                }
            ]
    
    def _find_task_for_agent(self, state: AgentState, agent_name: str) -> Optional[TaskPlan]:
        """Findet die passende Aufgabe für einen Agenten."""
        if not state.task_plan:
            return None
        
        for task in state.task_plan:
            if task.assigned_agent == agent_name or agent_name in task.task_id.lower():
                return task
        
        return None
    
    def _structure_agent_result(self, response: str, agent_config: Dict[str, Any]) -> Any:
        """Strukturiert das Agenten-Ergebnis basierend auf dem Output Schema."""
        output_schema = agent_config.get('output_schema')
        
        if not output_schema:
            return response
        
        try:
            # Dynamisches Import der Schema-Klasse
            from . import data_models
            schema_class = getattr(data_models, output_schema)
            
            # ▶️ Schritt 3.1: Spezielle Behandlung für QualityAssessment
            if output_schema == "QualityAssessment":
                # Versuche JSON zu parsen - für QualityAssessment ist das essentiell
                json_content = self._extract_json_from_response(response)
                if json_content:
                    logger.info(f"✅ QualityAssessment JSON erfolgreich extrahiert")
                    return schema_class.model_validate(json_content)
                else:
                    logger.error(f"❌ Fehler: QualityAssessment Agent gab kein valides JSON zurück")
                    # Fallback mit default-Werten
                    return QualityAssessment(
                        recommendation="fail",
                        reasoning="Agent konnte keine strukturierte Bewertung liefern",
                        issues_found=["Invalid JSON response from QA agent"],
                        confidence_score=0.1
                    )
            
            # Bestehende Logik für andere Schemas
            elif response.strip().startswith('{'):
                return schema_class.model_validate_json(response)
            else:
                # Fallback: Erstelle strukturiertes Objekt aus Text
                if output_schema == "ResearchReport":
                    return ResearchReport(
                        summary=response[:500] + "..." if len(response) > 500 else response,
                        findings=[],
                        confidence_score=0.7
                    )
                elif output_schema == "FinalReport":
                    return FinalReport(
                        title="Generated Report",
                        content=response,
                        references=[]
                    )
        
        except Exception as e:
            logger.warning(f"Failed to structure result for schema {output_schema}: {e}")
            return response
        
        return response
    
    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """
        Extrahiert JSON aus einer Agent-Antwort, auch wenn sie zusätzlichen Text enthält.
        """
        try:
            # Versuche den gesamten Response als JSON zu parsen
            if response.strip().startswith('{') and response.strip().endswith('}'):
                return json.loads(response.strip())
            
            # Suche nach JSON-Block in der Antwort
            import re
            json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
            matches = re.findall(json_pattern, response)
            
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
            
            # Fallback: Suche nach ```json Code-Blöcken
            json_block_pattern = r'```json\s*(\{.*?\})\s*```'
            json_blocks = re.findall(json_block_pattern, response, re.DOTALL)
            
            for block in json_blocks:
                try:
                    return json.loads(block)
                except json.JSONDecodeError:
                    continue
            
            return None
            
        except Exception as e:
            logger.warning(f"Error extracting JSON from response: {e}")
            return None
    
    async def _handle_conditional_transitions(self, 
                                            state: AgentState, 
                                            current_agent: str, 
                                            transitions: List[Dict[str, str]], 
                                            crew_config: Dict[str, Any]) -> str:
        """
        ▶️ Schritt 3.2: Robuste Routing-Logik für bedingte Übergänge.
        Wertet strukturierte QualityAssessment-Ergebnisse aus, um den nächsten Knoten zu bestimmen.
        
        Args:
            state: Aktueller Mission-Zustand
            current_agent: Aktuell abgeschlossener Agent
            transitions: Liste der möglichen Übergänge mit Bedingungen
            crew_config: Crew-Konfiguration
            
        Returns:
            str: Name des nächsten Agenten oder "END"
        """
        # Hole das strukturierte Ergebnis des aktuellen Agenten
        current_result = state.get_result(current_agent, "output")
        
        # ▶️ Neue robuste Logik: Prüfe ob es ein QualityAssessment ist
        if isinstance(current_result, QualityAssessment):
            logger.info(f"🎯 Verwende strukturierte QualityAssessment für Routing")
            return self._handle_quality_assessment_routing(current_result, transitions, state)
        
        # Fallback: Verwende die alte Supervisor-basierte Logik für andere Agent-Typen
        logger.info(f"⚠️ Fallback zu Supervisor-basiertem Routing für {current_agent}")
        return await self._handle_legacy_conditional_transitions(
            state, current_agent, transitions, crew_config
        )
    
    def _handle_quality_assessment_routing(self, 
                                         qa_result: QualityAssessment, 
                                         transitions: List[Dict[str, str]], 
                                         state: AgentState) -> str:
        """
        Deterministische Routing-Entscheidung basierend auf QualityAssessment.
        Dies ist jetzt typsicher und vorhersagbar.
        """
        recommendation = qa_result.recommendation.value
        
        # ▶️ Deterministische Mapping-Logik
        recommendation_to_target = {
            "publish": "END",
            "revise": "writer", 
            "research_more": "researcher",
            "fail": "END"
        }
        
        next_target = recommendation_to_target.get(recommendation)
        
        if next_target:
            logger.info(f"✅ QA-Routing: '{recommendation}' → '{next_target}' (Confidence: {qa_result.confidence_score:.2f})")
            
            # Logge Begründung für Transparenz
            state.add_history_entry(
                f"QA-Entscheidung: {recommendation} → {next_target} | "
                f"Begründung: {qa_result.reasoning} | "
                f"Confidence: {qa_result.confidence_score:.2f}"
            )
            
            # Logge Issues für nachgelagerte Agenten
            if qa_result.issues_found:
                state.add_history_entry(f"QA-Issues: {', '.join(qa_result.issues_found)}")
            
            return next_target
        
        # Fallback bei unbekannter Empfehlung
        logger.warning(f"❌ Unbekannte QA-Empfehlung: '{recommendation}'. Fallback zu END.")
        state.add_history_entry(f"FEHLER: Unbekannte QA-Empfehlung '{recommendation}' - beende Mission")
        return "END"
    
    async def _handle_legacy_conditional_transitions(self, 
                                                   state: AgentState, 
                                                   current_agent: str, 
                                                   transitions: List[Dict[str, str]], 
                                                   crew_config: Dict[str, Any]) -> str:
        """
        Legacy-Fallback: Supervisor-basierte Routing-Logik für Nicht-QA-Agenten.
        """
        # Hole das Ergebnis des aktuellen Agenten
        current_result = state.get_result(current_agent, "output")
        
        # Erstelle Routing-Prompt für den Supervisor
        routing_prompt = self._create_routing_prompt(state, current_agent, current_result, transitions)
        
        try:
            # Supervisor trifft die Routing-Entscheidung
            supervisor_model = crew_config.get('supervisor_model', 'gpt4o_via_or')
            routing_response = await self.bridge.bridge_message(
                conversation_id=f"{state.mission_id}_routing",
                target_llm_name=supervisor_model,
                message=routing_prompt
            )
            
            # Parse die Supervisor-Entscheidung
            next_agent = self._parse_routing_response(routing_response, transitions)
            
            state.add_history_entry(f"Legacy Supervisor routing: {current_agent} -> {next_agent}")
            logger.info(f"Legacy conditional routing: {current_agent} -> {next_agent}")
            
            return next_agent
            
        except Exception as e:
            logger.error(f"Conditional transition failed: {e}")
            # Fallback: Nimm den ersten verfügbaren Übergang
            if transitions:
                fallback_target = transitions[0]['target']
                state.add_history_entry(f"Routing fallback: {current_agent} -> {fallback_target}")
                return fallback_target
            return "END"
    
    def _create_routing_prompt(self, 
                              state: AgentState, 
                              current_agent: str, 
                              current_result: Any, 
                              transitions: List[Dict[str, str]]) -> str:
        """Erstellt den Prompt für Supervisor-Routing-Entscheidungen."""
        
        # Formatiere das aktuelle Ergebnis
        result_summary = str(current_result)[:500] + "..." if len(str(current_result)) > 500 else str(current_result)
        
        # Erstelle Optionen-Liste
        options_text = ""
        for i, transition in enumerate(transitions, 1):
            options_text += f"{i}. {transition['condition']} -> Ziel: {transition['target']}\n"
        
        # INTELLIGENCE LAYER: Dynamic Task Refinement Information
        current_plan_summary = self._get_current_plan_summary(state)
        
        prompt = f"""Du bist ein erfahrener Supervisor für Multi-Agenten-Workflows mit der Fähigkeit zur dynamischen Plananpassung.

MISSION: {state.high_level_goal}
AKTUELLER AGENT: {current_agent}
AGENT-ERGEBNIS: {result_summary}

BISHERIGE SCHRITTE:
{chr(10).join(state.history[-3:])}  # Zeige die letzten 3 Schritte

AKTUELLER PLAN:
{current_plan_summary}

VERFÜGBARE OPTIONEN:
{options_text}

AUFGABE:
1. Bewerte das Ergebnis des Agenten '{current_agent}'
2. Entscheide, ob der aktuelle Plan noch optimal ist
3. Wähle den nächsten Schritt

INTELLIGENCE LAYER - DYNAMIC REFINEMENT:
Falls das Ergebnis zeigt, dass der ursprüngliche Plan unzureichend ist, kannst du implizit eine Anpassung vorschlagen, indem du einen anderen Agent auswählst als ursprünglich geplant.

Antworte NUR mit dem Ziel-Namen (z.B. "writer", "researcher", oder "END"). Keine Erklärung nötig."""
        
        return prompt
    
    def _get_current_plan_summary(self, state: AgentState) -> str:
        """Erstellt eine Zusammenfassung des aktuellen Plans für Dynamic Task Refinement."""
        if not state.task_plan:
            return "Kein spezifischer Plan verfügbar"
        
        plan_summary = "Aktueller Aufgabenplan:\n"
        for i, task in enumerate(state.task_plan, 1):
            status = "✅ Abgeschlossen" if task.assigned_agent in state.completed_nodes else "⏳ Ausstehend"
            plan_summary += f"{i}. {task.description} (Agent: {task.assigned_agent}) - {status}\n"
        
        return plan_summary
    
    def _parse_routing_response(self, response: str, transitions: List[Dict[str, str]]) -> str:
        """Parsed die Supervisor-Routing-Antwort."""
        response = response.strip().lower()
        
        # Suche nach einem gültigen Ziel in der Antwort
        valid_targets = [t['target'].lower() for t in transitions]
        
        for target in valid_targets:
            if target in response:
                # Gib das original-case Target zurück
                for transition in transitions:
                    if transition['target'].lower() == target:
                        return transition['target']
        
        # Fallback: Wenn nichts gefunden, nimm das erste verfügbare Ziel
        if transitions:
            return transitions[0]['target']
        
        return "END"
    
    # ▶️ REMOVED: _handle_human_intervention Methode - ersetzt durch Exception-basierte Pausierung
    # Die neue Logik pausiert die Mission komplett und wartet auf externe Fortsetzung via API
    
    async def _check_quality_threshold(self, 
                                     state: AgentState, 
                                     crew_config: Dict[str, Any]) -> bool:
        """
        ADVANCED LAYER: Prüft ob die Qualitätsschwelle erreicht wurde.
        
        Args:
            state: Aktueller Mission-Zustand
            crew_config: Crew-Konfiguration
            
        Returns:
            bool: True wenn Qualität ausreichend ist
        """
        quality_threshold = crew_config.get('quality_threshold', 0.8)
        
        # Suche nach dem letzten QA-Report
        qa_results = [result for agent_name, result in state.results.items() 
                     if 'qa' in agent_name.lower()]
        
        if not qa_results:
            return False
            
        latest_qa = qa_results[-1]
        if hasattr(latest_qa, 'overall_score'):
            return latest_qa.overall_score >= quality_threshold
        elif isinstance(latest_qa, dict) and 'overall_score' in latest_qa:
            return latest_qa['overall_score'] >= quality_threshold
            
        return False
    
    async def _check_iteration_limit(self, 
                                   state: AgentState, 
                                   crew_config: Dict[str, Any]) -> bool:
        """
        ADVANCED LAYER: Prüft ob das Iterationslimit erreicht wurde.
        
        Args:
            state: Aktueller Mission-Zustand
            crew_config: Crew-Konfiguration
            
        Returns:
            bool: True wenn Limit erreicht
        """
        max_iterations = crew_config.get('max_iterations', 3)
        
        # Zähle Durchläufe durch den Graphen
        iteration_count = len([entry for entry in state.history 
                             if 'completed successfully' in entry])
        
        return iteration_count >= max_iterations
    
    def get_mission_status(self, mission_id: str) -> Optional[Dict[str, Any]]:
        """Holt den Status einer laufenden Mission (für zukünftige Implementierung)."""
        # Placeholder für Zukunft - könnte mit Redis/DB implementiert werden
        return None
    
    async def execute_template_mission(self, template_name: str, parameters: Dict[str, Any], active_missions_dict: Optional[Dict[str, Any]] = None) -> AgentState:
        """Führt eine Mission basierend auf einem Template aus."""
        if template_name not in self.mission_templates:
            raise ValueError(f"Template '{template_name}' nicht gefunden")
        
        template = self.mission_templates[template_name]
        crew_name = template['crew']
        
        # Erstelle Goal aus Template
        prompt_template = template['prompt_template']
        goal = prompt_template.format(**parameters)
        
        return await self.execute_mission(crew_name, goal, parameters, active_missions_dict)
    
    def _serialize_for_json(self, obj: Any) -> Any:
        """Serialisiert Objekte für JSON, behandelt datetime-Objekte sicher."""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._serialize_for_json(item) for item in obj]
        elif hasattr(obj, 'model_dump'):
            # Pydantic-Objekte
            return self._serialize_for_json(obj.model_dump())
        else:
            return obj