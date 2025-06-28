# llm_bridge/tools/registry.py
"""
Tool Registry für die LLM2LLM-Bridge
====================================

Zentrale Verwaltung aller verfügbaren Tools für Agenten.
"""

from .web_tools import search_web, fetch_url_content, analyze_content


# ▶️ Schritt 1.1: Definieren der benutzerdefinierten Exception.
# Sie dient als Signal vom Tool zum Orchestrator.
class HumanInterventionRequired(Exception):
    """
    Exception die ausgelöst wird, wenn ein Agent menschliche Hilfe benötigt.
    Diese Exception wird vom AgentOrchestrator gefangen und in eine 
    Human-Request-Schleife umgewandelt.
    """
    def __init__(self, request_details: 'HumanRequest'):
        self.request_details = request_details
        super().__init__(f"Menschliche Intervention erforderlich: {request_details.question}")


# ▶️ Schritt 1.2: Definieren der Funktion, die die Exception auslöst.
def ask_human(question: str, context: str = "", options: list = None, urgency: str = "medium") -> str:
    """
    Ein spezielles 'Tool', das von einem Agenten aufgerufen werden kann.
    Es führt keine Aktion aus, sondern signalisiert dem Orchestrator durch eine Exception,
    dass die Mission pausiert und auf menschliche Eingabe gewartet werden muss.
    Der Rückgabewert wird nie erreicht, ist aber für die Typ-Signatur wichtig.
    
    Args:
        question: Die spezifische Frage an den Menschen
        context: Zusätzlicher Kontext für besseres Verständnis
        options: Optionale Liste von Antwortmöglichkeiten
        urgency: Dringlichkeit (low, medium, high)
    
    Raises:
        HumanInterventionRequired: Immer - wird vom Orchestrator gefangen
    
    Returns:
        str: Wird nie erreicht, aber für Typ-Hinting benötigt
    """
    from ..orchestration.data_models import HumanRequest  # Lokaler Import, um Zirkelbezüge zu vermeiden
    
    request = HumanRequest(
        agent_name="unknown",  # Der Orchestrator wird dies später ersetzen
        question=question,
        context=context,
        options=options,
        urgency=urgency
    )
    raise HumanInterventionRequired(request)


TOOL_REGISTRY = {
    "web_search": {
        "function": search_web,
        "description": "Führt eine Websuche durch, um aktuelle Informationen zu einem Thema zu finden",
        "parameters": {
            "query": {"type": "str", "description": "Die Suchanfrage"},
            "max_results": {"type": "int", "description": "Maximale Anzahl Ergebnisse (optional)", "default": 5}
        },
        "category": "web",
        "async": True
    },
    
    "fetch_url": {
        "function": fetch_url_content,
        "description": "Lädt den Inhalt einer spezifischen URL",
        "parameters": {
            "url": {"type": "str", "description": "Die zu ladende URL"}
        },
        "category": "web",
        "async": True
    },
    
    "analyze_content": {
        "function": analyze_content,
        "description": "Analysiert gegebenen Text (Zusammenfassung, Keywords, Sentiment)",
        "parameters": {
            "content": {"type": "str", "description": "Zu analysierender Text"},
            "analysis_type": {"type": "str", "description": "Art der Analyse: summary, keywords, sentiment", "default": "summary"}
        },
        "category": "analysis",
        "async": True
    },
    
    # ▶️ Schritt 1.3: Registrieren des neuen Tools.
    "ask_human": {
        "function": ask_human,
        "description": "Pausiert die Mission und stellt eine spezifische Frage an einen menschlichen Experten. Benutze dies nur, wenn du absolut nicht weiterkommst oder eine strategische Entscheidung benötigst.",
        "parameters": {
            "question": {"type": "str", "description": "Die spezifische Frage an den Menschen"},
            "context": {"type": "str", "description": "Zusätzlicher Kontext für besseres Verständnis", "default": ""},
            "options": {"type": "list", "description": "Optionale Liste von Antwortmöglichkeiten", "default": None},
            "urgency": {"type": "str", "description": "Dringlichkeit: low, medium, high", "default": "medium"}
        },
        "category": "collaboration",
        "async": False
    },
    
    # Placeholder für zukünftige Tools
    "document_analysis": {
        "function": lambda doc: {"status": "simulated", "analysis": f"Dokument-Analyse für {doc}"},
        "description": "Analysiert Dokumente und extrahiert wichtige Informationen",
        "parameters": {
            "document": {"type": "str", "description": "Pfad oder Inhalt des Dokuments"}
        },
        "category": "analysis",
        "async": False
    },
    
    "quality_check": {
        "function": lambda content: {"status": "simulated", "quality_score": 0.85, "suggestions": ["Verbesserung 1", "Verbesserung 2"]},
        "description": "Überprüft die Qualität von erstellten Inhalten",
        "parameters": {
            "content": {"type": "str", "description": "Zu überprüfender Inhalt"}
        },
        "category": "quality",
        "async": False
    },
    
    "text_formatting": {
        "function": lambda text: {"status": "simulated", "formatted_text": f"Formatierter Text: {text}"},
        "description": "Formatiert und strukturiert Text für bessere Lesbarkeit",
        "parameters": {
            "text": {"type": "str", "description": "Zu formatierender Text"}
        },
        "category": "formatting",
        "async": False
    },
    
    "grammar_check": {
        "function": lambda text: {"status": "simulated", "corrections": [], "score": 0.95},
        "description": "Überprüft Grammatik und Rechtschreibung",
        "parameters": {
            "text": {"type": "str", "description": "Zu überprüfender Text"}
        },
        "category": "quality",
        "async": False
    },
    
    "data_processing": {
        "function": lambda data: {"status": "simulated", "processed_data": f"Verarbeitete Daten: {data}"},
        "description": "Verarbeitet und analysiert strukturierte Daten",
        "parameters": {
            "data": {"type": "str", "description": "Zu verarbeitende Daten"}
        },
        "category": "analysis",
        "async": False
    },
    
    "chart_generation": {
        "function": lambda data: {"status": "simulated", "chart_url": "https://example.com/chart.png"},
        "description": "Erstellt Diagramme und Visualisierungen aus Daten",
        "parameters": {
            "data": {"type": "str", "description": "Daten für die Visualisierung"}
        },
        "category": "visualization",
        "async": False
    },
    
    # ADVANCED LAYER: Human-in-the-Loop Tool
    "ask_human": {
        "function": ask_human,
        "description": "Stelle eine klärende Frage an den menschlichen Benutzer, wenn eine Aufgabe mehrdeutig ist oder menschliches Urteilsvermögen erfordert. Löst eine Exception aus, die vom Orchestrator behandelt wird.",
        "parameters": {
            "question": {"type": "str", "description": "Die spezifische Frage an den Menschen"},
            "context": {"type": "str", "description": "Zusätzlicher Kontext", "default": ""},
            "options": {"type": "list", "description": "Optionale Antwortmöglichkeiten", "default": []},
            "urgency": {"type": "str", "description": "Dringlichkeit: low, medium, high", "default": "medium"}
        },
        "category": "human_interaction",
        "async": False
    }
}


def get_tool_by_name(tool_name: str):
    """Holt ein Tool aus der Registry."""
    return TOOL_REGISTRY.get(tool_name)


def get_tools_by_category(category: str):
    """Holt alle Tools einer bestimmten Kategorie."""
    return {name: tool for name, tool in TOOL_REGISTRY.items() 
            if tool.get('category') == category}


def list_available_tools():
    """Gibt eine Liste aller verfügbaren Tool-Namen zurück."""
    return list(TOOL_REGISTRY.keys())


def get_tool_description(tool_name: str) -> str:
    """Gibt die Beschreibung eines Tools zurück."""
    tool = TOOL_REGISTRY.get(tool_name)
    return tool.get('description', 'Kein Tool gefunden') if tool else 'Kein Tool gefunden'