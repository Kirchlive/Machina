# app/core/adapters/universal_adapter.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AdapterError(Exception):
    """Benutzerdefinierte Exception für Adapter-Fehler."""
    pass

class UniversalAdapter(ABC):
    """
    Eine abstrakte Basisklasse, die als einheitliche Schnittstelle
    für alle Plattform-Adapter (API, Browser, Desktop, CLI) dient.
    """
    def __init__(self, model_config: Dict[str, Any]):
        self.config = model_config
        self.platform = model_config.get('platform', 'api')
        self.tool_name = model_config.get('tool_name', model_config.get('name', 'Unknown'))
        print(f"INFO: Initializing adapter for '{self.tool_name}' with platform type '{self.platform}'")

    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """Die Kernmethode zur Ausführung einer Konversationsanfrage."""
        pass