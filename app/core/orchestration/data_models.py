# llm_bridge/orchestration/data_models.py
"""
Pydantic-Modelle für die strukturierte Kommunikation zwischen Agenten.
Inspiriert von MetaGPT's "Standardized Operating Procedures".
"""
from enum import Enum
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

# ▶️ Schritt 1.1: Definieren der möglichen, festen Empfehlungen als Enum.
# Dies verhindert Tippfehler und macht den Code lesbarer.
class Recommendation(str, Enum):
    PUBLISH = "publish"
    REVISE = "revise"
    RESEARCH_MORE = "research_more"
    FAIL = "fail"

class ResearchFinding(BaseModel):
    """Ein einzelner, zitierbarer Fakt oder eine Erkenntnis."""
    finding: str = Field(description="Die Kernaussage oder der Datenpunkt.")
    source: str = Field(description="Die URL oder der Name der Quelle.")
    quote: Optional[str] = Field(default=None, description="Ein direktes Zitat aus der Quelle.")
    relevance_score: float = Field(default=0.8, description="Relevanz für das Thema (0-1)")

class ResearchReport(BaseModel):
    """Ein strukturierter Bericht, der vom Researcher-Agenten erstellt wird."""
    summary: str = Field(description="Eine kurze Zusammenfassung der wichtigsten Erkenntnisse.")
    findings: List[ResearchFinding] = Field(description="Eine Liste von detaillierten Fakten.")
    confidence_score: float = Field(default=0.9, description="Ein Wert zwischen 0 und 1, wie sicher der Agent bei seinen Ergebnissen ist.")
    research_scope: str = Field(default="general", description="Beschreibung des Recherche-Umfangs")
    timestamp: datetime = Field(default_factory=datetime.now, description="Zeitstempel der Erstellung")

class FinalReport(BaseModel):
    """Das finale, vom Writer-Agenten erstellte und vom Supervisor abgenommene Dokument."""
    title: str = Field(description="Aussagekräftiger Titel des Berichts")
    content: str = Field(description="Der vollständige Bericht-Inhalt")
    references: List[str] = Field(description="Liste der verwendeten Quellen")
    word_count: Optional[int] = Field(default=None, description="Anzahl der Wörter im Content")
    quality_score: float = Field(default=0.9, description="Selbsteinschätzung der Qualität (0-1)")

class TaskPlan(BaseModel):
    """Ein strukturierter Aufgabenplan vom Supervisor."""
    task_id: str = Field(description="Eindeutige Identifikation der Aufgabe")
    description: str = Field(description="Detaillierte Beschreibung der Aufgabe")
    assigned_agent: str = Field(description="Name des zugewiesenen Agenten")
    expected_output: str = Field(description="Erwartete Art des Outputs")
    priority: int = Field(default=1, description="Priorität der Aufgabe (1=höchste)")

# ▶️ Schritt 1.2: Definieren des Pydantic-Modells für die Ausgabe des QA-Agenten.
# Dies ist der "Datenvertrag", an den sich der Agent halten muss.
class QualityAssessment(BaseModel):
    """
    Strukturierte Qualitätsbewertung vom QA-Agenten für robuste Conditional Transitions.
    Ersetzt die fragile Freitext-Interpretation durch einen deterministischen Ansatz.
    """
    recommendation: Recommendation = Field(
        ..., 
        description="Die klare Empfehlung für den nächsten Schritt. Muss einer der vordefinierten Werte sein."
    )
    reasoning: str = Field(
        ..., 
        description="Eine kurze, menschlesbare Begründung für die Entscheidung."
    )
    strengths: List[str] = Field(
        default_factory=list, 
        description="Eine Liste der positiven Aspekte der Arbeit."
    )
    issues_found: List[str] = Field(
        default_factory=list,
        description="Eine Liste der konkreten Probleme, die behoben werden müssen."
    )
    confidence_score: float = Field(
        default=0.9, 
        ge=0.0, 
        le=1.0, 
        description="Ein Wert zwischen 0 und 1, wie sicher der Agent bei seiner Bewertung ist."
    )
    
    # Legacy-Kompatibilität für bestehende Workflows
    @property
    def overall_quality(self) -> float:
        """Legacy-Kompatibilität: Leitet Gesamtqualität aus confidence_score ab."""
        return self.confidence_score
    
    @property
    def next_agent(self) -> str:
        """Legacy-Kompatibilität: Leitet nächsten Agent aus recommendation ab."""
        mapping = {
            Recommendation.PUBLISH: "END",
            Recommendation.REVISE: "writer", 
            Recommendation.RESEARCH_MORE: "researcher",
            Recommendation.FAIL: "END"
        }
        return mapping.get(self.recommendation, "END")

class QAReport(BaseModel):
    """ADVANCED LAYER: Detaillierter QA-Bericht für Automated Feedback Loops."""
    overall_score: float = Field(ge=0, le=1, description="Gesamtbewertung der Arbeit (0-1)")
    critical_issues: List[str] = Field(default_factory=list, description="Kritische Probleme die behoben werden müssen")
    minor_issues: List[str] = Field(default_factory=list, description="Kleinere Verbesserungsmöglichkeiten")
    strengths: List[str] = Field(default_factory=list, description="Positive Aspekte der Arbeit")
    feedback_summary: str = Field(description="Zusammenfassung des Feedbacks für den nächsten Agenten")
    meets_requirements: bool = Field(description="Erfüllt die Arbeit die ursprünglichen Anforderungen?")
    recommendation: str = Field(description="Empfehlung: 'publish' (END), 'revise' (zurück an Writer), 'research_more' (zurück an Researcher)")
    revision_count: int = Field(default=0, description="Anzahl bisheriger Überarbeitungen")
    estimated_completion: float = Field(ge=0, le=1, description="Geschätzte Vollständigkeit (0-1)")

class HumanRequest(BaseModel):
    """ADVANCED LAYER: Struktur für Human-in-the-Loop Anfragen."""
    agent_name: str = Field(description="Name des Agenten der um Hilfe bittet")
    question: str = Field(description="Die spezifische Frage an den Menschen")
    context: str = Field(description="Kontext und bisherige Arbeit")
    options: Optional[List[str]] = Field(default=None, description="Optionale Antwortmöglichkeiten")
    urgency: str = Field(default="medium", description="Dringlichkeit: low, medium, high")
    timeout_seconds: Optional[int] = Field(default=300, description="Timeout für die Antwort in Sekunden")

class MissionStatus(BaseModel):
    """Status-Update einer laufenden Mission."""
    mission_id: str
    current_step: str
    progress_percentage: float = Field(ge=0, le=100)
    status: str = Field(description="PENDING, RUNNING, COMPLETED, ERROR, AWAITING_HUMAN_INPUT")
    message: Optional[str] = Field(default=None, description="Zusätzliche Statusnachricht")
    human_request: Optional[HumanRequest] = Field(default=None, description="ADVANCED: Aktuelle Human-Request falls status=AWAITING_HUMAN_INPUT")