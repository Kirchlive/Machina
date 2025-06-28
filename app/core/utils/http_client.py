"""
Zentraler HTTP-Client-Manager für asynchrone Netzwerkanfragen mit Connection Pooling.

Dieser Manager verwaltet eine einzige httpx.AsyncClient-Instanz für die gesamte
Anwendungslebensdauer, um effizientes Connection Pooling und Ressourcen-Management
zu ermöglichen.

Autor: Claude AI
Erstellt: 2024-12-20 (Roadmap Step 2.1)
"""

import httpx
from typing import Optional
import asyncio


class HTTPClientManager:
    """
    Verwaltet eine globale, asynchrone httpx.AsyncClient-Instanz,
    um Connection Pooling über die gesamte Anwendung hinweg zu ermöglichen.
    
    Diese Klasse implementiert das Singleton-Pattern für HTTP-Clients und
    bietet optimierte Einstellungen für LLM-API-Calls.
    """
    
    _client: Optional[httpx.AsyncClient] = None
    _lock = asyncio.Lock()

    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """
        Gibt die globale Client-Instanz zurück. Erstellt sie thread-safe, falls sie nicht existiert.
        
        Returns:
            httpx.AsyncClient: Die globale, konfigurierte Client-Instanz
        """
        # Double-checked locking pattern für thread-safety
        if cls._client is None or cls._client.is_closed:
            async with cls._lock:
                # Nochmal prüfen nach dem Lock
                if cls._client is None or cls._client.is_closed:
                    cls._client = cls._create_client()
                    print("🌐 [HTTP] Neuer globaler HTTP-Client erstellt mit Connection Pooling")
        
        return cls._client

    @classmethod
    def _create_client(cls) -> httpx.AsyncClient:
        """
        Erstellt eine neue httpx.AsyncClient-Instanz mit optimalen Einstellungen.
        
        Returns:
            httpx.AsyncClient: Konfigurierte Client-Instanz
        """
        # Timeout-Konfiguration für LLM-APIs
        # - connect: 5s (Verbindungsaufbau)
        # - read: 120s (LLM-Antworten können lange dauern)
        # - write: 10s (Request senden)
        # - pool: 10s (Warten auf verfügbare Connection)
        timeout = httpx.Timeout(
            connect=5.0,
            read=120.0,  # LLMs können lange antworten
            write=10.0,
            pool=10.0
        )
        
        # Connection Pool Limits
        # - max_keepalive_connections: Anzahl wiederverwendbarer Verbindungen
        # - max_connections: Maximale Gesamtverbindungen
        limits = httpx.Limits(
            max_keepalive_connections=50,  # Für multiple LLM-Provider
            max_connections=200,           # Hoher Durchsatz
            keepalive_expiry=300.0         # 5 Minuten Keep-Alive
        )
        
        return httpx.AsyncClient(
            timeout=timeout,
            limits=limits,
            http2=False,                   # HTTP/2 deaktiviert (h2 package nicht erforderlich)
            follow_redirects=True,         # Automatische Redirect-Behandlung
            verify=True                    # SSL-Verifikation für Sicherheit
        )

    @classmethod
    async def close_client(cls):
        """
        Schließt die globale Client-Instanz sauber und gibt Ressourcen frei.
        
        Diese Methode sollte beim Anwendungs-Shutdown aufgerufen werden.
        """
        async with cls._lock:
            if cls._client and not cls._client.is_closed:
                print("🔒 [HTTP] Schließe globalen HTTP-Client...")
                await cls._client.aclose()
                cls._client = None
                print("✅ [HTTP] HTTP-Client erfolgreich geschlossen")

    @classmethod
    def get_client_info(cls) -> dict:
        """
        Gibt Informationen über den aktuellen Client-Status zurück.
        
        Returns:
            dict: Status-Informationen des HTTP-Clients
        """
        if cls._client is None:
            return {"status": "not_initialized"}
        
        if cls._client.is_closed:
            return {"status": "closed"}
        
        # Verbindungspool-Statistiken
        pool_info = {}
        if hasattr(cls._client, '_transport') and cls._client._transport:
            transport = cls._client._transport
            if hasattr(transport, '_pool'):
                pool = transport._pool
                pool_info = {
                    "active_connections": len(getattr(pool, '_connections', [])),
                    "keepalive_connections": len(getattr(pool, '_keepalive_connections', [])),
                }
        
        return {
            "status": "active",
            "http2_enabled": False,  # HTTP/2 deaktiviert
            "pool_info": pool_info,
            "timeout_config": {
                "connect": cls._client.timeout.connect,
                "read": cls._client.timeout.read,
                "write": cls._client.timeout.write,
                "pool": cls._client.timeout.pool,
            }
        }

    @classmethod
    async def health_check(cls) -> bool:
        """
        Führt einen einfachen Health Check des HTTP-Clients durch.
        
        Returns:
            bool: True wenn der Client funktionsfähig ist
        """
        try:
            client = await cls.get_client()
            # Einfacher HTTP-Test (httpbin.org für Tests)
            response = await client.get("https://httpbin.org/status/200", timeout=5.0)
            return response.status_code == 200
        except Exception as e:
            print(f"⚠️ [HTTP] Health Check fehlgeschlagen: {e}")
            return False


# Convenience-Funktionen für direkten Zugriff
async def get_http_client() -> httpx.AsyncClient:
    """Convenience-Funktion für direkten Zugriff auf den HTTP-Client."""
    return await HTTPClientManager.get_client()


async def http_get(url: str, **kwargs) -> httpx.Response:
    """Convenience-Funktion für GET-Requests."""
    client = await get_http_client()
    return await client.get(url, **kwargs)


async def http_post(url: str, **kwargs) -> httpx.Response:
    """Convenience-Funktion für POST-Requests."""
    client = await get_http_client()
    return await client.post(url, **kwargs)