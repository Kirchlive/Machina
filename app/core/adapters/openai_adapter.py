from .base_adapter import BaseAdapter
from ..utils.http_client import HTTPClientManager
import json

class OpenAIAdapter(BaseAdapter):
    """
    Ein dedizierter Adapter für die native OpenAI API.
    Verwendet den zentralen HTTP-Client für optimales Connection Pooling.
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openai.com/v1"
        
        # Basis-Headers für alle Requests
        self._base_headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    async def send(self, prompt: str, model: str = "gpt-4", **kwargs) -> str:
        """
        Sendet einen Prompt an das spezifizierte OpenAI-Modell.
        Verwendet den zentralen HTTP-Client für optimales Connection Pooling.

        Args:
            prompt (str): Der Input-Prompt.
            model (str): Das zu verwendende OpenAI-Modell (z.B. "gpt-4", "gpt-3.5-turbo").
            **kwargs: Zusätzliche Parameter wie 'max_tokens', 'temperature'.

        Returns:
            str: Die Antwort des LLM.
        """
        # Bereite Request-Payload vor
        max_tokens = kwargs.pop('max_tokens', 2048)
        endpoint = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            **kwargs  # Zusätzliche Parameter wie temperature
        }
        
        # Verwende den zentralen HTTP-Client
        client = await HTTPClientManager.get_client()
        
        try:
            print(f"🤖 [HTTP] Sending request to OpenAI {model}")
            
            response = await client.post(
                endpoint,
                json=payload,
                headers=self._base_headers
            )
            
            # Prüfe HTTP-Status
            response.raise_for_status()
            
            # Parse JSON Response
            data = response.json()
            
            # Extrahiere Antwort gemäß OpenAI API Format
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                return content.strip() if content else ""
            else:
                raise ValueError(f"Unexpected OpenAI response format: {data}")
                
        except Exception as e:
            print(f"❌ [HTTP] Error in OpenAIAdapter for model '{model}': {e}")
            # Re-raise für Circuit Breaker
            raise e