# app/core/plugins/claude_plugin.py
"""
Claude AI Plugin
================

Plugin für die Integration von Claude AI (Anthropic) in die LLM2LLM-Bridge.
Verwendet den nativen Claude Adapter für direkte API-Kommunikation.
"""

import os
from .base_plugin import LLMAdapterPlugin
from ..adapters.claude_adapter import ClaudeAdapter


class ClaudePlugin(LLMAdapterPlugin):
    """Plugin für Claude AI (Anthropic) Integration."""
    
    @property
    def name(self) -> str:
        return "claude_service"
    
    @property
    def description(self) -> str:
        return "Claude AI (Anthropic) - Direkter API-Zugang für optimale Performance"
    
    @property
    def api_key_env_var(self) -> str:
        return "CLAUDE_API_KEY"
    
    def create_adapter(self, model_config=None):
        """Erstellt eine konfigurierte Claude-Adapter-Instanz."""
        api_key = os.getenv(self.api_key_env_var)
        
        if not api_key:
            raise ValueError(
                f"Claude API-Schlüssel nicht gefunden. "
                f"Bitte setzen Sie {self.api_key_env_var} in der .env-Datei."
            )
        
        return ClaudeAdapter(api_key=api_key)