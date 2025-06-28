# app/core/di/interfaces.py
"""
Interface re-export for backwards compatibility.
The actual interfaces are in the interfaces/ subdirectory.
"""

from .interfaces import *  # Re-export all interfaces

# This file exists to satisfy import paths that expect
# app.core.di.interfaces to be a module file rather than a directory