# app/core/plugins/gemini_plugin.py
"""
Google Gemini Plugin
====================

Plugin für die Integration von Google Gemini in die LLM2LLM-Bridge.
Verwendet den nativen Gemini Adapter für direkte API-Kommunikation.
"""

import os
from .base_plugin import LLMAdapterPlugin
from ..adapters.gemini_adapter import GeminiAdapter


class GeminiPlugin(LLMAdapterPlugin):
    """Plugin für Google Gemini Integration."""
    
    @property
    def name(self) -> str:
        return "gemini_service"
    
    @property
    def description(self) -> str:
        return "Google Gemini - Multimodaler AI-Assistent von Google"
    
    @property
    def api_key_env_var(self) -> str:
        return "GOOGLE_API_KEY"
    
    def create_adapter(self, model_config=None):
        """Erstellt eine konfigurierte Gemini-Adapter-Instanz."""
        api_key = os.getenv(self.api_key_env_var)
        
        if not api_key:
            raise ValueError(
                f"Google API-Schlüssel nicht gefunden. "
                f"Bitte setzen Sie {self.api_key_env_var} in der .env-Datei."
            )
        
        return GeminiAdapter(api_key=api_key)