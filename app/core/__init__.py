# Macht die Core-Klasse leicht importierbar
from .core import LLMBridgeCore

# Nur ausgeben wenn nicht in Test-Umgebung
import os
import sys

# Prüfe ob wir in pytest laufen
if not any('pytest' in arg for arg in sys.argv) and not os.environ.get('PYTEST_CURRENT_TEST'):
    print("📦 LLM Bridge Package Initialized")