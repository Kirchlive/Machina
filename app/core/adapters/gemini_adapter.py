# app/core/adapters/gemini_adapter.py

from .base_adapter import BaseAdapter
from ..utils.http_client import HTTPClientManager
import json

class GeminiAdapter(BaseAdapter):
    """
    Ein dedizierter Adapter für die native Google Gemini API.
    Verwendet den zentralen HTTP-Client für optimales Connection Pooling.
    """
    def __init__(self, api_key: str):
        """
        Konfiguriert die Google Gemini API mit dem bereitgestellten Schlüssel.
        """
        self.api_key = api_key
        self.base_url = "https://generativelanguage.googleapis.com/v1beta"
        
        # Basis-Headers für alle Requests
        self._base_headers = {
            "Content-Type": "application/json"
        }

    async def send(self, prompt: str, model: str, **kwargs) -> str:
        """
        Sendet einen Prompt an das spezifizierte Gemini-Modell.
        Verwendet den zentralen HTTP-Client für optimales Connection Pooling.

        Args:
            prompt (str): Der Input-Prompt.
            model (str): Das zu verwendende Gemini-Modell (z.B. "gemini-1.5-pro-latest").
            **kwargs: Zusätzliche Parameter für die Generierung.

        Returns:
            str: Die Antwort des LLM.
        """
        if not model:
            return "Error: Ein 'model'-Parameter ist für den GeminiAdapter zwingend erforderlich."

        # Bereite Request-Payload vor
        endpoint = f"{self.base_url}/models/{model}:generateContent?key={self.api_key}"
        
        payload = {
            "contents": [{
                "parts": [{
                    "text": prompt
                }]
            }],
            "generationConfig": {
                "maxOutputTokens": kwargs.get('max_tokens', 2048),
                "temperature": kwargs.get('temperature', 0.7),
                "topP": kwargs.get('top_p', 0.8),
                "topK": kwargs.get('top_k', 10)
            }
        }
        
        # Verwende den zentralen HTTP-Client
        client = await HTTPClientManager.get_client()
        
        try:
            print(f"🔮 [HTTP] Sending request to Gemini {model}")
            
            response = await client.post(
                endpoint,
                json=payload,
                headers=self._base_headers
            )
            
            # Prüfe HTTP-Status
            response.raise_for_status()
            
            # Parse JSON Response
            data = response.json()
            
            # Extrahiere Antwort gemäß Gemini API Format
            if "candidates" in data and len(data["candidates"]) > 0:
                candidate = data["candidates"][0]
                if "content" in candidate and "parts" in candidate["content"]:
                    content = candidate["content"]["parts"][0]["text"]
                    return content.strip() if content else ""
                else:
                    raise ValueError(f"No content in Gemini response: {data}")
            else:
                raise ValueError(f"Unexpected Gemini response format: {data}")
                
        except Exception as e:
            print(f"❌ [HTTP] Error in GeminiAdapter for model '{model}': {e}")
            # Re-raise für Circuit Breaker
            raise e