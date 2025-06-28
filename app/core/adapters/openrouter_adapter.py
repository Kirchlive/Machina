# In llm_bridge/adapters/openrouter_adapter.py

from .base_adapter import BaseAdapter
from ..utils.http_client import HTTPClientManager
import json

# Der Klassenname wurde hier final geändert
class OpenRouterAdapter(BaseAdapter):
    """
    Ein universeller Adapter, optimiert für OpenAI-kompatible APIs wie OpenRouter.
    Er kann jede API ansteuern, die der OpenAI-Spezifikation folgt.
    """
    def __init__(self, api_key: str, base_url: str = None, extra_headers: dict = None):
        """
        Initialisiert den Adapter.

        Args:
            api_key (str): Der API-Schlüssel für den Dienst.
            base_url (str, optional): Die Basis-URL der API. Notwendig für OpenRouter.
            extra_headers (dict, optional): Zusätzliche HTTP-Header (z.B. für Rankings).
        """
        # Speichere Parameter für HTTP-Requests
        self.api_key = api_key
        self.base_url = base_url or "https://openrouter.ai/api/v1"
        self.extra_headers = extra_headers or {}
        
        # Basis-Headers für alle Requests
        self._base_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            **self.extra_headers
        }

    async def send(self, prompt: str, model: str, **kwargs) -> str:
        """
        Sendet einen Prompt an das spezifizierte Modell über die konfigurierte API.
        Verwendet den zentralen HTTP-Client für optimales Connection Pooling.

        Args:
            prompt (str): Der Input-Prompt.
            model (str): Das zu verwendende Modell (z.B. "openai/gpt-4o" oder "deepseek-r1:latest").
            **kwargs: Zusätzliche API-Parameter (inkl. dynamische base_url).

        Returns:
            str: Die Antwort des LLM.
        """
        if not model:
            return "Error: Ein 'model'-Parameter ist für den OpenRouterAdapter zwingend erforderlich."
        
        # Dynamische base_url für Ollama etc.
        # Wenn eine base_url in kwargs übergeben wird, hat diese Vorrang.
        dynamic_base_url = kwargs.pop('base_url', self.base_url)
        endpoint = f"{dynamic_base_url.rstrip('/')}/chat/completions"
        
        # Bereite Request-Payload vor
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            **kwargs  # Zusätzliche Parameter wie temperature, max_tokens, etc.
        }
        
        # Verwende den zentralen HTTP-Client
        client = await HTTPClientManager.get_client()
        
        try:
            print(f"🌐 [HTTP] Sending request to {endpoint} with model {model}")
            
            response = await client.post(
                endpoint,
                json=payload,
                headers=self._base_headers
            )
            
            # Prüfe HTTP-Status
            response.raise_for_status()
            
            # Parse JSON Response
            data = response.json()
            
            # Extrahiere Antwort
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else ""
            else:
                raise ValueError(f"Unexpected response format: {data}")
                
        except Exception as e:
            print(f"❌ [HTTP] Error in OpenRouterAdapter for model '{model}' at '{endpoint}': {e}")
            # Re-raise für Circuit Breaker
            raise e