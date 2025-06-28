# llm_bridge/plugins/base_plugin.py
"""
LLM Adapter Plugin Interface
============================

Definiert die abstrakte Basisklasse für alle LLM-Adapter-Plugins.
Jedes Plugin muss von dieser Klasse erben und die erforderlichen Methoden implementieren.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict


class LLMAdapterPlugin(ABC):
    """
    Abstrakte Basisklasse für LLM-Adapter-Plugins.
    
    Ein Plugin fungiert als Factory für LLM-Adapter und stellt sicher, dass
    jeder Adapter korrekt konfiguriert und einsatzbereit ist.
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """
        Der eindeutige Name des Adapters (z.B. 'claude_service', 'openai_service').
        
        Dieser Name wird verwendet, um den Adapter in der Bridge zu registrieren
        und muss eindeutig sein.
        
        Returns:
            str: Eindeutiger Adapter-Name
        """
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """
        Eine kurze Beschreibung des Adapters.
        
        Returns:
            str: Beschreibung des Adapters
        """
        pass

    @abstractmethod
    def create_adapter(self, model_config: Dict[str, Any] = None) -> Any:
        """
        Erstellt und konfiguriert eine Instanz des LLM-Adapters.
        
        Diese Methode ist dafür verantwortlich:
        - API-Schlüssel aus Umgebungsvariablen zu laden
        - Den Adapter zu konfigurieren
        - Fehler bei fehlenden Konfigurationen zu behandeln
        
        Args:
            model_config: Optional - Modellkonfiguration aus models.yaml
        
        Returns:
            Any: Eine konfigurierte Adapter-Instanz
            
        Raises:
            ValueError: Wenn erforderliche Konfiguration fehlt
            Exception: Bei anderen Konfigurationsfehlern
        """
        pass

    @property
    def requires_api_key(self) -> bool:
        """
        Gibt an, ob dieser Adapter einen API-Schlüssel benötigt.
        
        Returns:
            bool: True wenn API-Schlüssel erforderlich, False sonst
        """
        return True

    @property
    def api_key_env_var(self) -> str:
        """
        Name der Umgebungsvariable für den API-Schlüssel.
        
        Returns:
            str: Name der Umgebungsvariable (z.B. 'CLAUDE_API_KEY')
        """
        return f"{self.name.upper()}_API_KEY"

    def is_available(self, model_config: Dict[str, Any] = None) -> bool:
        """
        Prüft, ob der Adapter verfügbar ist (z.B. API-Schlüssel vorhanden).
        
        Args:
            model_config: Optional - Modellkonfiguration aus models.yaml
        
        Returns:
            bool: True wenn verfügbar, False sonst
        """
        if not self.requires_api_key:
            return True
        
        import os
        return bool(os.getenv(self.api_key_env_var))

    def get_status_info(self) -> dict:
        """
        Gibt Status-Informationen über das Plugin zurück.
        
        Returns:
            dict: Status-Informationen
        """
        return {
            "name": self.name,
            "description": self.description,
            "requires_api_key": self.requires_api_key,
            "api_key_env_var": self.api_key_env_var,
            "is_available": self.is_available()
        }