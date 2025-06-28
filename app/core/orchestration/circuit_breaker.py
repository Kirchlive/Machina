# llm_bridge/orchestration/circuit_breaker.py

import asyncio
import random
from datetime import datetime, timedelta
from enum import Enum
from typing import Type, Optional

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"      # Anfragen werden durchgelassen
    OPEN = "OPEN"          # Anfragen werden sofort abgewiesen
    HALF_OPEN = "HALF_OPEN"  # Eine einzelne Test-Anfrage wird durchgelassen

# Alias für Backwards-Kompatibilität
State = CircuitBreakerState

class CircuitBreakerError(Exception):
    """Wird ausgelöst, wenn der Circuit Breaker offen ist."""
    def __init__(self, message: str, next_attempt_at: Optional[datetime] = None):
        super().__init__(message)
        self.next_attempt_at = next_attempt_at

class CircuitBreaker:
    """
    Ein verbesserter Circuit Breaker, der eine Funktion vor wiederholten Fehlern schützt.
    Implementiert Exponential Backoff mit Jitter, um eine intelligente Wiederherstellung zu ermöglichen.
    """
    def __init__(
        self,
        event_store=None,
        adapter_name: str = "unknown",
        max_failures: int = 3,
        reset_timeout: int = 60,  # Basis-Timeout für Backwards-Kompatibilität
        reset_timeout_base_seconds: Optional[int] = None,
        max_reset_timeout_seconds: int = 300,
        expected_exception: Type[Exception] = Exception
    ):
        # Backwards-Kompatibilität mit alten Parametern
        self._event_store = event_store
        self._adapter_name = adapter_name
        self._max_failures = max_failures
        
        # Neue Parameter für Exponential Backoff
        self._reset_timeout_base_seconds = reset_timeout_base_seconds or reset_timeout
        self._max_reset_timeout_seconds = max_reset_timeout_seconds
        self._expected_exception = expected_exception

        # State Management
        self._failure_count = 0
        self._consecutive_failure_count = 0  # Für Exponential Backoff
        self._state = CircuitBreakerState.CLOSED
        self._last_failure_time: Optional[datetime] = None
        self._next_attempt_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitBreakerState:
        """Gibt den aktuellen Zustand des Circuit Breakers zurück."""
        # Diese Property sollte nicht die State ändern, um Thread-Safety zu gewährleisten
        return self._state
    
    @property
    def event_store(self):
        """Backwards-Kompatibilität für event_store Property."""
        return self._event_store
    
    @property
    def adapter_name(self):
        """Backwards-Kompatibilität für adapter_name Property."""
        return self._adapter_name

    async def execute(self, coro):
        """Führt eine Coroutine aus und wendet die Circuit Breaker Logik an."""
        async with self._lock:
            if self._state == CircuitBreakerState.OPEN:
                if self._next_attempt_at and datetime.now() >= self._next_attempt_at:
                    # Die Wartezeit ist abgelaufen, wir versuchen einen einzelnen Request
                    self._state = CircuitBreakerState.HALF_OPEN
                    if self._event_store:
                        await self._event_store.log_circuit_breaker_event(
                            adapter_name=self._adapter_name,
                            event="TRANSITION_TO_HALF_OPEN",
                            details=f"Wartezeit abgelaufen, teste Verfügbarkeit"
                        )
                else:
                    # Circuit ist noch offen
                    if self._event_store:
                        await self._event_store.log_circuit_breaker_event(
                            adapter_name=self._adapter_name,
                            event="REQUEST_BLOCKED_OPEN_STATE"
                        )
                    
                    error_msg = f"Circuit is open for '{self._adapter_name}'. Service is temporarily unavailable."
                    if self._next_attempt_at:
                        error_msg += f" Next attempt at {self._next_attempt_at.isoformat()}"
                    
                    raise CircuitBreakerError(error_msg, self._next_attempt_at)
        
        # Im HALF_OPEN oder CLOSED Zustand, führen wir die Anfrage aus
        try:
            result = await coro
        except self._expected_exception as e:
            await self.record_failure()
            raise e
        except Exception as e:
            # Nicht erwartete Exceptions führen nicht zu Circuit Breaker Aktivierung
            raise e
        
        await self.record_success()
        return result

    async def record_success(self):
        """Wird bei einer erfolgreichen Anfrage aufgerufen."""
        async with self._lock:
            previous_state = self._state
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                print(f"[Circuit Breaker] {self._adapter_name}: Erfolgreicher Test-Request. Schließe den Kreis.")
                if self._event_store:
                    await self._event_store.log_circuit_breaker_event(
                        adapter_name=self._adapter_name,
                        event="RESET_TO_CLOSED",
                        details="Test-Request erfolgreich"
                    )
            
            self._failure_count = 0
            self._consecutive_failure_count = 0
            self._state = CircuitBreakerState.CLOSED
            self._next_attempt_at = None

    async def record_failure(self):
        """Wird bei einer fehlgeschlagenen Anfrage aufgerufen."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = datetime.now()
            
            if self._state == CircuitBreakerState.HALF_OPEN:
                # Der Test-Request ist fehlgeschlagen, wir öffnen den Kreis wieder mit verlängerter Wartezeit
                self._consecutive_failure_count += 1
                print(f"[Circuit Breaker] {self._adapter_name}: Test-Request fehlgeschlagen. Öffne den Kreis erneut.")
                if self._event_store:
                    await self._event_store.log_circuit_breaker_event(
                        adapter_name=self._adapter_name,
                        event="TEST_REQUEST_FAILED",
                        failure_count=self._failure_count,
                        details=f"Consecutive failures: {self._consecutive_failure_count}"
                    )
                self._open_circuit()
            elif self._failure_count >= self._max_failures:
                self._consecutive_failure_count = 1  # Erste Öffnung nach CLOSED state
                print(f"[Circuit Breaker] {self._adapter_name}: Fehler-Schwelle ({self._max_failures}) erreicht. Öffne den Kreis.")
                if self._event_store:
                    await self._event_store.log_circuit_breaker_event(
                        adapter_name=self._adapter_name,
                        event="TRIPPED_TO_OPEN",
                        failure_count=self._failure_count
                    )
                self._open_circuit()

    def _open_circuit(self):
        """Öffnet den Circuit Breaker und berechnet die nächste Wiederholungszeit."""
        self._state = CircuitBreakerState.OPEN
        
        # Exponential Backoff Berechnung
        # Bei jedem konsekutiven Fehler verdoppelt sich die Wartezeit
        backoff_multiplier = 2 ** (self._consecutive_failure_count - 1)
        backoff_duration = self._reset_timeout_base_seconds * backoff_multiplier
        
        # Begrenze die maximale Wartezeit
        capped_backoff = min(backoff_duration, self._max_reset_timeout_seconds)
        
        # Jitter hinzufügen (zufällige Varianz von ±20%), um "Thundering Herd" zu vermeiden
        jitter_factor = random.uniform(0.8, 1.2)
        final_wait_time = capped_backoff * jitter_factor
        
        self._next_attempt_at = datetime.now() + timedelta(seconds=final_wait_time)
        
        print(f"[Circuit Breaker] {self._adapter_name}: Nächster Versuch in {final_wait_time:.2f} Sekunden "
              f"(Backoff: {capped_backoff}s, Jitter: {jitter_factor:.2f})")
        
    # Backwards-kompatible Helper-Methoden
    async def _log_event(self, event: str, **kwargs):
        """Helper für Event-Logging."""
        if self._event_store:
            await self._event_store.log_circuit_breaker_event(
                adapter_name=self._adapter_name,
                event=event,
                **kwargs
            )