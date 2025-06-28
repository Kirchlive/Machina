# app/core/adapters/claude_adapter.py

from .base_adapter import BaseAdapter
from ..utils.http_client import HTTPClientManager
import json

class ClaudeAdapter(BaseAdapter):
    """
    Ein dedizierter Adapter für die native Anthropic Claude API.
    Verwendet den zentralen HTTP-Client für optimales Connection Pooling.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.anthropic.com/v1"
        
        # Basis-Headers für alle Requests
        self._base_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "anthropic-version": "2023-06-01"
        }

    async def send(self, prompt: str, model: str, **kwargs) -> str:
        """
        Sendet einen Prompt an das spezifizierte Claude-Modell.
        Verwendet den zentralen HTTP-Client für optimales Connection Pooling.

        Args:
            prompt (str): Der Input-Prompt.
            model (str): Das zu verwendende Claude-Modell (z.B. "claude-3.5-sonnet").
            **kwargs: Zusätzliche Parameter wie 'max_tokens'.

        Returns:
            str: Die Antwort des LLM.
        """
        if not model:
            return "Error: Ein 'model'-Parameter ist für den ClaudeAdapter zwingend erforderlich."

        # Bereite Request-Payload vor
        max_tokens = kwargs.pop('max_tokens', 2048)
        endpoint = f"{self.base_url}/messages"
        
        payload = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            **kwargs  # Zusätzliche Parameter wie temperature
        }
        
        # Verwende den zentralen HTTP-Client
        client = await HTTPClientManager.get_client()
        
        try:
            print(f"🧠 [HTTP] Sending request to Claude {model}")
            
            response = await client.post(
                endpoint,
                json=payload,
                headers=self._base_headers
            )
            
            # Prüfe HTTP-Status
            response.raise_for_status()
            
            # Parse JSON Response
            data = response.json()
            
            # Extrahiere Antwort gemäß Claude API Format
            if "content" in data and len(data["content"]) > 0:
                content = data["content"][0]["text"]
                return content.strip() if content else ""
            else:
                raise ValueError(f"Unexpected Claude response format: {data}")
                
        except Exception as e:
            print(f"❌ [HTTP] Error in ClaudeAdapter for model '{model}': {e}")
            # Re-raise für Circuit Breaker
            raise e