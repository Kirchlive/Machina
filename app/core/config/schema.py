# Datei: llm_bridge/config/schema.py

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Any, Optional, Union


class CostConfig(BaseModel):
    input_per_million_tokens: float
    output_per_million_tokens: float


class ModelConfig(BaseModel):
    adapter_service: str
    provider: Optional[str] = None  # CLI-Modelle haben keinen Provider
    context_window: Optional[int] = None  # CLI-Modelle haben kein context_window
    cost: Optional[CostConfig] = None  # CLI-Modelle haben keine Kosten
    capabilities: Optional[List[str]] = None  # CLI-Modelle haben keine capabilities
    notes: Optional[str] = None
    model_name_direct: Optional[str] = None
    model_name_openrouter: Optional[str] = None
    # CLI-spezifische Felder
    platform: Optional[str] = None
    tool_name: Optional[str] = None
    command: Optional[str] = None
    execution_env: Optional[str] = None
    interaction_mode: Optional[str] = None


class AgentConfig(BaseModel):
    model: str
    role: str
    goal: str
    backstory: str
    tools: List[str]
    output_schema: str
    max_iterations: int
    temperature: float
    input_schema: Optional[str] = None  # Für erweiterte Agenten


class ConditionalTransition(BaseModel):
    condition: str
    target: str


class NodeConfig(BaseModel):
    transitions_to: Optional[str] = None
    conditional_transitions: Optional[List[ConditionalTransition]] = None

    @model_validator(mode='before')
    @classmethod
    def check_transitions(cls, values):
        """Stellt sicher, dass entweder transitions_to oder conditional_transitions vorhanden ist."""
        transitions_to = values.get('transitions_to')
        conditional_transitions = values.get('conditional_transitions')
        
        if transitions_to and conditional_transitions:
            raise ValueError("Ein Knoten kann nicht sowohl 'transitions_to' als auch 'conditional_transitions' haben.")
        if not transitions_to and not conditional_transitions:
            raise ValueError("Ein Knoten muss entweder 'transitions_to' oder 'conditional_transitions' definieren.")
        return values


class GraphConfig(BaseModel):
    entry_point: str
    nodes: Dict[str, NodeConfig]

    @model_validator(mode='after')
    def entry_point_must_exist_in_nodes(self):
        """Prüft, ob der entry_point tatsächlich in den nodes definiert ist."""
        if self.entry_point not in self.nodes:
            raise ValueError(f"Entry point '{self.entry_point}' muss in nodes definiert sein")
        return self


class CrewConfig(BaseModel):
    name: str
    description: str
    agents: List[str]
    supervisor_model: str
    graph: GraphConfig
    expected_deliverables: Optional[List[str]] = None
    max_execution_time: Optional[int] = 3600  # Standard: 1 Stunde
    max_iterations: Optional[int] = 3
    quality_threshold: Optional[float] = 0.85


class MissionTemplateConfig(BaseModel):
    crew: str
    goal: Optional[str] = None
    prompt_template: Optional[str] = None
    required_params: Optional[List[str]] = None


class RegistrySchema(BaseModel):
    """
    Hauptschema für die Registry-Validierung.
    Verwendet einen speziellen Build-Mechanismus für dynamische Model-Keys.
    """
    models: Dict[str, ModelConfig]
    agents: Dict[str, AgentConfig]
    crews: Dict[str, CrewConfig]
    mission_templates: Dict[str, MissionTemplateConfig] = Field(default_factory=dict)
    
    class Config:
        # Erlaube zusätzliche Felder für Backwards-Kompatibilität
        extra = "allow"

    @classmethod
    def build_from_yaml_data(cls, data: Dict[str, Any]) -> 'RegistrySchema':
        """Bereitet die rohen YAML-Daten für die Pydantic-Validierung vor."""
        known_keys = {'agents', 'crews', 'mission_templates', '_registry_info', '_model_templates'}
        
        # Alle unbekannten Schlüssel auf oberster Ebene werden als Modelle interpretiert
        # AUSSER _model_templates (YAML-Anker-Definitionen)
        model_data = {k: v for k, v in data.items() if k not in known_keys}
        
        # Bereinigte Daten für die Validierung
        validation_data = {
            'models': model_data,
            'agents': data.get('agents', {}),
            'crews': data.get('crews', {}),
            'mission_templates': data.get('mission_templates', {})
        }
        return cls.model_validate(validation_data)

    @model_validator(mode='after')
    def cross_reference_validation(self):
        """
        Kernvalidierung: Prüft alle Referenzen innerhalb der Konfiguration.
        Dies ist das Herzstück der Robustheit.
        """
        all_models = self.models
        all_agents = self.agents
        all_crews = self.crews
        all_templates = self.mission_templates
        
        # 1. Prüfe, ob das Modell jedes Agenten existiert
        for agent_name, agent_config in all_agents.items():
            if agent_config.model not in all_models:
                raise ValueError(f"Agent '{agent_name}' referenziert ein nicht-existierendes Modell: '{agent_config.model}'")
        
        # 2. Prüfe Crew-Konfigurationen
        for crew_name, crew_config in all_crews.items():
            # Supervisor-Modell muss existieren
            if crew_config.supervisor_model not in all_models:
                raise ValueError(f"Crew '{crew_name}' referenziert ein nicht-existierendes Supervisor-Modell: '{crew_config.supervisor_model}'")
            
            # Alle Agenten der Crew müssen existieren
            for agent_in_crew in crew_config.agents:
                if agent_in_crew not in all_agents:
                    raise ValueError(f"Crew '{crew_name}' referenziert einen nicht-existierenden Agenten: '{agent_in_crew}'")
            
            # Graph-Knoten müssen den verfügbaren Agenten entsprechen
            graph_nodes = set(crew_config.graph.nodes.keys())
            available_agents = set(crew_config.agents)
            
            # Warnung für Knoten, die nicht als Agenten definiert sind (z.B. "END")
            undefined_nodes = graph_nodes - available_agents - {"END"}
            if undefined_nodes:
                print(f"⚠️ Warnung: Crew '{crew_name}' hat Graph-Knoten ohne entsprechende Agenten: {undefined_nodes}")
        
        # 3. Prüfe Mission Templates
        for template_name, template_config in all_templates.items():
            if template_config.crew not in all_crews:
                raise ValueError(f"Mission Template '{template_name}' referenziert eine nicht-existierende Crew: '{template_config.crew}'")

        return self

    def get_model_names(self) -> List[str]:
        """Hilfsmethode: Gibt alle verfügbaren Modellnamen zurück."""
        return list(self.models.keys())

    def get_agent_names(self) -> List[str]:
        """Hilfsmethode: Gibt alle verfügbaren Agentennamen zurück."""
        return list(self.agents.keys())

    def get_crew_names(self) -> List[str]:
        """Hilfsmethode: Gibt alle verfügbaren Crew-Namen zurück."""
        return list(self.crews.keys())

    def validate_model_availability(self, required_models: List[str]) -> List[str]:
        """Prüft, welche der angeforderten Modelle verfügbar sind."""
        available = self.get_model_names()
        missing = [model for model in required_models if model not in available]
        return missing