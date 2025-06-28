# LLM2LLM-Bridge Plugin System

## Überblick

Das Plugin-System ermöglicht es, neue LLM-Adapter hinzuzufügen, ohne den Kerncode der Bridge zu modifizieren. Jedes Plugin ist eine Python-Datei in diesem Verzeichnis, die eine spezifische Schnittstelle implementiert.

## Plugin-Struktur

Ein Plugin muss von der `LLMAdapterPlugin`-Basisklasse erben und zwei Eigenschaften implementieren:

```python
from .base_plugin import LLMAdapterPlugin
from ..adapters.your_adapter import YourAdapter

class YourPlugin(LLMAdapterPlugin):
    @property
    def name(self) -> str:
        return "your_service"  # Eindeutiger Name für den Adapter
    
    @property
    def adapter_class(self):
        # Rückgabe einer Adapter-Instanz
        api_key = os.getenv("YOUR_API_KEY")
        return YourAdapter(api_key=api_key)
```

## Automatisches Laden

Alle `.py`-Dateien in diesem Verzeichnis (außer `__init__.py` und `base_plugin.py`) werden beim Start der Bridge automatisch geladen und registriert.

## Beispiele

- `claude_plugin.py` - Claude AI Integration
- `gemini_plugin.py` - Google Gemini Integration
- `openrouter_plugin.py` - OpenRouter Gateway

## API-Key Verwaltung

Jedes Plugin ist selbst dafür verantwortlich, seine API-Schlüssel aus Umgebungsvariablen zu laden. Fehlende Schlüssel sollten eine aussagekräftige Fehlermeldung produzieren.