"""
HTTP Client Service Implementation

Manages HTTP client instances with connection pooling and lifecycle management.
"""

import httpx
from typing import Optional, Dict, Any
import logging
from app.core.di.interfaces import IHTTPClientProvider

class HTTPClientService(IHTTPClientProvider):
    """
    Concrete implementation of IHTTPClientProvider
    
    Provides managed HTTP client instances with:
    - Connection pooling
    - Configurable timeouts
    - Proper lifecycle management
    """
    
    def __init__(self, 
                 timeout: int = 30,
                 max_connections: int = 100,
                 max_keepalive_connections: int = 20,
                 keepalive_expiry: float = 5.0,
                 verify_ssl: bool = True):
        """
        Initialize the HTTP client service
        
        Args:
            timeout: Default timeout in seconds
            max_connections: Maximum number of connections
            max_keepalive_connections: Maximum keepalive connections
            keepalive_expiry: Keepalive expiry in seconds
            verify_ssl: Whether to verify SSL certificates
        """
        self._timeout = timeout
        self._max_connections = max_connections
        self._max_keepalive_connections = max_keepalive_connections
        self._keepalive_expiry = keepalive_expiry
        self._verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None
        self._logger = logging.getLogger(__name__)
        
    async def get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client instance"""
        if self._client is None:
            limits = httpx.Limits(
                max_connections=self._max_connections,
                max_keepalive_connections=self._max_keepalive_connections,
                keepalive_expiry=self._keepalive_expiry
            )
            
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                limits=limits,
                verify=self._verify_ssl,
                follow_redirects=True
            )
            
            self._logger.debug(
                f"Created HTTP client with timeout={self._timeout}s, "
                f"max_connections={self._max_connections}"
            )
            
        return self._client
    
    async def close(self) -> None:
        """Close the HTTP client and cleanup resources"""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._logger.debug("HTTP client closed")
    
    async def request(self, 
                     method: str,
                     url: str,
                     **kwargs) -> httpx.Response:
        """
        Convenience method for making HTTP requests
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            **kwargs: Additional arguments passed to httpx
            
        Returns:
            HTTP response
        """
        client = await self.get_client()
        return await client.request(method, url, **kwargs)
    
    async def get(self, url: str, **kwargs) -> httpx.Response:
        """Make a GET request"""
        return await self.request("GET", url, **kwargs)
    
    async def post(self, url: str, **kwargs) -> httpx.Response:
        """Make a POST request"""
        return await self.request("POST", url, **kwargs)
    
    def configure_timeout(self, timeout: int) -> None:
        """Update the timeout configuration"""
        self._timeout = timeout
        if self._client:
            # If client exists, we need to recreate it with new timeout
            self._logger.info(f"Timeout changed to {timeout}s, client will be recreated")
            # Close existing client on next get_client() call
            self._client = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.get_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

class HTTPClientManager:
    """
    Legacy compatibility layer for existing HTTPClientManager usage
    
    This wraps HTTPClientService to maintain backward compatibility
    while transitioning to dependency injection.
    """
    
    _instance: Optional[HTTPClientService] = None
    
    @classmethod
    def get_instance(cls) -> HTTPClientService:
        """Get singleton instance (for backward compatibility)"""
        if cls._instance is None:
            cls._instance = HTTPClientService()
        return cls._instance
    
    @classmethod
    async def get_client(cls) -> httpx.AsyncClient:
        """Get HTTP client (for backward compatibility)"""
        instance = cls.get_instance()
        return await instance.get_client()
    
    @classmethod
    async def close(cls) -> None:
        """Close HTTP client (for backward compatibility)"""
        if cls._instance:
            await cls._instance.close()
            cls._instance = None