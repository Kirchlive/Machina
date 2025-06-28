# app/core/plugins/openai_plugin.py
"""
OpenAI Plugin
=============

Plugin für die Integration von OpenAI GPT-Modellen in die LLM2LLM-Bridge.
Nutzt den nativen OpenAI Adapter für direkte API-Kommunikation.
"""

import os
from .base_plugin import LLMAdapterPlugin
from ..adapters.openai_adapter import OpenAIAdapter


class OpenAIPlugin(LLMAdapterPlugin):
    """Plugin für OpenAI GPT-Modelle Integration."""
    
    @property
    def name(self) -> str:
        return "openai_service"
    
    @property
    def description(self) -> str:
        return "OpenAI GPT Models - Direct API access for GPT-4, GPT-3.5 and other OpenAI models"
    
    @property
    def api_key_env_var(self) -> str:
        return "OPENAI_API_KEY"
    
    def create_adapter(self, model_config=None):
        """
        Erstellt einen OpenAI-Adapter mit den bereitgestellten Konfigurationen.
        
        Args:
            model_config (dict): Modell-spezifische Konfiguration aus registry.yaml
            
        Returns:
            OpenAIAdapter: Konfigurierte Adapter-Instanz
        """
        api_key = os.getenv(self.api_key_env_var)
        if not api_key:
            raise ValueError(f"API key not found. Please set {self.api_key_env_var}")
        
        # Create the adapter with just the API key
        # The OpenAIAdapter expects only api_key in constructor
        return OpenAIAdapter(api_key=api_key)
    
    def get_status_info(self) -> dict:
        """Gibt Status-Informationen über das Plugin zurück."""
        return {
            "description": self.description,
            "api_key_configured": bool(os.getenv(self.api_key_env_var)),
            "supported_models": [
                "gpt-4-turbo-preview",
                "gpt-4",
                "gpt-3.5-turbo",
                "gpt-4o",
                "gpt-4o-mini"
            ]
        }