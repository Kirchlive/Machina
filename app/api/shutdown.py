# Datei: api_server/shutdown.py

import asyncio
import signal
import sys
import os
from typing import List, Callable, Coroutine
from datetime import datetime
import logging

# Add parent directory to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.core.utils.task_manager import get_task_manager, create_background_task

logger = logging.getLogger(__name__)

class GracefulShutdownHandler:
    """
    Eine Klasse zur Verwaltung eines sauberen Herunterfahrens der Anwendung.
    Sie fängt OS-Signale ab und führt registrierte Cleanup-Aufgaben aus.
    """
    def __init__(self):
        self.is_shutting_down = False
        self._cleanup_callbacks: List[Callable[[], Coroutine]] = []
        self._shutdown_start_time = None

    def register_cleanup(self, callback: Callable[[], Coroutine]):
        """Registriert eine asynchrone Cleanup-Funktion."""
        self._cleanup_callbacks.append(callback)
        print(f"[SHUTDOWN] Cleanup-Callback registriert: {callback.__name__}")

    def setup_signal_handlers(self):
        """
        Richtet die Signal-Handler für SIGINT (Ctrl+C) und SIGTERM ein.
        """
        # Skip signal handler setup in test environment
        if os.getenv("TESTING", "").lower() == "true":
            print("[SHUTDOWN] Signal-Handler übersprungen (Test-Modus)")
            return
            
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGINT, self._signal_handler)
            loop.add_signal_handler(signal.SIGTERM, self._signal_handler)
            print("[SHUTDOWN] Signal-Handler für SIGINT und SIGTERM eingerichtet (Unix-Modus)")
        except NotImplementedError:
            # add_signal_handler ist unter Windows nicht für SIGINT/SIGTERM verfügbar
            # Wir verwenden signal.signal als Fallback
            try:
                signal.signal(signal.SIGINT, self._signal_handler_sync)
                signal.signal(signal.SIGTERM, self._signal_handler_sync)
                print("[SHUTDOWN] Signal-Handler für SIGINT und SIGTERM eingerichtet (Windows-Modus)")
            except ValueError as e:
                # Can happen in threads or test environments
                print(f"[SHUTDOWN] Signal-Handler konnte nicht eingerichtet werden: {e}")

    def _signal_handler_sync(self, signum, frame):
        """Synchroner Wrapper für den Signal-Handler (Windows-Kompatibilität)."""
        # Erstelle eine Task für den asynchronen Handler
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running() and not loop.is_closed():
                # Verwende asyncio.create_task direkt um Rekursion zu vermeiden
                asyncio.create_task(self._signal_handler(signum))
            else:
                # Fallback für nicht-async Kontexte
                print(f"\n[SHUTDOWN] Signal {signum} erhalten. Sofortiges Beenden.")
                sys.exit(0)
        except RuntimeError:
            # Event loop is already closed
            print(f"\n[SHUTDOWN] Signal {signum} erhalten. Sofortiges Beenden.")
            sys.exit(0)
    
    async def _signal_handler(self, signum: int):
        """Leitet den Shutdown-Prozess ein."""
        if self.is_shutting_down:
            print("\n[SHUTDOWN] Zweite Aufforderung zum Herunterfahren erhalten. Erzwinge Beendigung.")
            sys.exit(1)
        
        signal_name = signal.Signals(signum).name if hasattr(signal, 'Signals') else str(signum)
        print(f"\n[SHUTDOWN] Signal {signal_name} erhalten. Starte sauberes Herunterfahren...")
        self.is_shutting_down = True
        self._shutdown_start_time = datetime.now()
        
        # Geben Sie dem Load Balancer (falls vorhanden) Zeit, die Instanz aus der Rotation zu nehmen.
        print("[SHUTDOWN] Warte 2 Sekunden für Load Balancer...")
        await asyncio.sleep(2)

        await self._run_cleanup()
        
        # Geben Sie laufenden Tasks noch einen Moment Zeit
        tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
        if tasks:
            print(f"[SHUTDOWN] Warte auf den Abschluss von {len(tasks)} verbleibenden Aufgaben...")
            # Geben Sie den Tasks maximal 10 Sekunden Zeit
            done, pending = await asyncio.wait(tasks, timeout=10.0)
            if pending:
                print(f"[SHUTDOWN] {len(pending)} Aufgaben wurden nach Timeout abgebrochen.")
                for task in pending:
                    task.cancel()

        shutdown_duration = (datetime.now() - self._shutdown_start_time).total_seconds()
        print(f"[SHUTDOWN] Herunterfahren abgeschlossen in {shutdown_duration:.2f} Sekunden. Auf Wiedersehen!")
        
        # Stoppe den Event Loop
        loop = asyncio.get_running_loop()
        loop.stop()

    async def _run_cleanup(self):
        """Führt alle registrierten Cleanup-Callbacks aus."""
        print(f"[SHUTDOWN] Führe {len(self._cleanup_callbacks)} Cleanup-Aufgaben aus...")
        
        # First shutdown the task manager to prevent new tasks
        task_manager = get_task_manager()
        active_tasks = task_manager.active_task_count
        if active_tasks > 0:
            print(f"[SHUTDOWN] Shutting down {active_tasks} background tasks...")
            cancelled = await task_manager.shutdown(timeout=5.0)
            print(f"[SHUTDOWN] {cancelled} background tasks were cancelled")
        
        # Then run regular cleanup callbacks
        for i, callback in enumerate(reversed(self._cleanup_callbacks), 1):
            try:
                callback_name = getattr(callback, '__name__', str(callback))
                print(f"[SHUTDOWN] [{i}/{len(self._cleanup_callbacks)}] Führe Cleanup aus: {callback_name}")
                await callback()
                print(f"[SHUTDOWN] [{i}/{len(self._cleanup_callbacks)}] Cleanup erfolgreich: {callback_name}")
            except Exception as e:
                print(f"[SHUTDOWN] Fehler während des Cleanups bei Callback '{callback_name}': {e}")

    async def wait_for_shutdown(self):
        """
        Eine Hilfsmethode, die es erlaubt, auf das Shutdown-Signal zu warten.
        Nützlich für Tests oder spezielle Anwendungsfälle.
        """
        while not self.is_shutting_down:
            await asyncio.sleep(0.1)