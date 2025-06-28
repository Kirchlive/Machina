# llm_bridge/tools/__init__.py
"""
Tool System für die LLM2LLM-Bridge
==================================

Ermöglicht Agenten die Nutzung externer Werkzeuge für erweiterte Funktionalität.
"""

from .registry import TOOL_REGISTRY
from .web_tools import search_web

__all__ = ['TOOL_REGISTRY', 'search_web']