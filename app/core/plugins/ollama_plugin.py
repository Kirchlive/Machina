# app/core/plugins/ollama_plugin.py
"""
Ollama Plugin
=============

Plugin für die Integration von Ollama (lokale LLM-Server) in die LLM2LLM-Bridge.
Ollama bietet OpenAI-kompatible API für lokale Modelle.
"""

import os
import requests
from .base_plugin import LLMAdapterPlugin
from ..adapters.openrouter_adapter import OpenRouterAdapter


class OllamaPlugin(LLMAdapterPlugin):
    """Plugin für Ollama lokale LLM-Server Integration."""
    
    @property
    def name(self) -> str:
        return "ollama_service"
    
    @property
    def description(self) -> str:
        return "Ollama - Lokale LLM-Server mit OpenAI-kompatibler API"
    
    @property
    def requires_api_key(self) -> bool:
        return False  # Ollama benötigt keinen API-Schlüssel
    
    def is_available(self, model_config=None) -> bool:
        """Prüft ob Ollama-Server erreichbar ist."""
        try:
            # Teste Verbindung zu lokalem Ollama-Server
            ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
            response = requests.get(f"{ollama_host}/api/tags", timeout=3)
            return response.status_code == 200
        except Exception:
            return False
    
    def create_adapter(self, model_config=None):
        """Erstellt eine konfigurierte Ollama-Adapter-Instanz."""
        
        if not model_config:
            raise ValueError("Ollama-Adapter benötigt eine Modellkonfiguration")
        
        # Ollama verwendet OpenAI-kompatible API
        ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434")
        base_url = f"{ollama_host}/v1"
        
        # OpenRouterAdapter wiederverwenden (da OpenAI-kompatibel)
        # Der model-Parameter wird später in der send()-Methode übergeben
        return OpenRouterAdapter(
            api_key="ollama",  # Dummy-Key (wird ignoriert)
            base_url=base_url,
            extra_headers={}
        )