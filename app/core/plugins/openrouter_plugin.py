# app/core/plugins/openrouter_plugin.py
"""
OpenRouter Plugin
=================

Plugin für die Integration von OpenRouter als universeller LLM-Gateway.
OpenRouter bietet Zugang zu verschiedenen LLMs über eine einheitliche API.
"""

import os
from .base_plugin import LLMAdapterPlugin
from ..adapters.openrouter_adapter import OpenRouterAdapter


class OpenRouterPlugin(LLMAdapterPlugin):
    """Plugin für OpenRouter Gateway Integration."""
    
    @property
    def name(self) -> str:
        return "openrouter_gateway"
    
    @property
    def description(self) -> str:
        return "OpenRouter Gateway - Universeller Zugang zu verschiedenen LLMs"
    
    @property
    def api_key_env_var(self) -> str:
        return "OPENROUTER_API_KEY"
    
    def create_adapter(self, model_config=None):
        """Erstellt eine konfigurierte OpenRouter-Adapter-Instanz."""
        api_key = os.getenv(self.api_key_env_var)
        
        if not api_key:
            raise ValueError(
                f"OpenRouter API-Schlüssel nicht gefunden. "
                f"Bitte setzen Sie {self.api_key_env_var} in der .env-Datei."
            )
        
        base_url = "https://openrouter.ai/api/v1"
        
        # OpenRouter-spezifische Header für Site-Tracking
        site_url = os.getenv("YOUR_SITE_URL", "http://localhost:8000")
        site_name = os.getenv("YOUR_SITE_NAME", "LLM2LLM-Bridge")
        
        extra_headers = {
            "HTTP-Referer": site_url,
            "X-Title": site_name
        }
        
        return OpenRouterAdapter(
            api_key=api_key,
            base_url=base_url,
            extra_headers=extra_headers
        )