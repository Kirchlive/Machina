# app/core/di/__init__.py
"""
Dependency Injection module for LLM2LLM-Bridge
"""

from .container import ServiceContainer
from .interfaces import *  # Re-export all interfaces

__all__ = ['ServiceContainer']