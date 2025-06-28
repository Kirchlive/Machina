"""
Redis Provider Service Implementation

Manages Redis connections with proper lifecycle management and connection pooling.
"""

from typing import Optional, Dict, Any
import logging
import asyncio
from redis.asyncio import Redis, ConnectionPool
from app.core.di.interfaces import IRedisProvider

class RedisProviderService(IRedisProvider):
    """
    Concrete implementation of IRedisProvider
    
    Provides managed Redis connections with:
    - Connection pooling
    - Automatic reconnection
    - Proper lifecycle management
    """
    
    def __init__(self,
                 host: str = 'localhost',
                 port: int = 6379,
                 db: int = 0,
                 password: Optional[str] = None,
                 decode_responses: bool = True,
                 max_connections: int = 50,
                 socket_timeout: int = 30,
                 socket_connect_timeout: int = 30):
        """
        Initialize the Redis provider
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (if required)
            decode_responses: Whether to decode responses to strings
            max_connections: Maximum number of connections in pool
            socket_timeout: Socket timeout in seconds
            socket_connect_timeout: Socket connection timeout
        """
        self._config = {
            'host': host,
            'port': port,
            'db': db,
            'password': password,
            'decode_responses': decode_responses,
            'max_connections': max_connections,
            'socket_timeout': socket_timeout,
            'socket_connect_timeout': socket_connect_timeout
        }
        
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[Redis] = None
        self._logger = logging.getLogger(__name__)
        
    async def get_client(self) -> Redis:
        """Get or create Redis client instance"""
        if self._client is None:
            await self._create_client()
            
        # Test connection
        try:
            await self._client.ping()
        except Exception as e:
            self._logger.warning(f"Redis connection lost: {e}, reconnecting...")
            await self._create_client()
            
        return self._client
    
    async def _create_client(self) -> None:
        """Create Redis client with connection pool"""
        try:
            # Create connection pool if not exists
            if self._pool is None:
                self._pool = ConnectionPool(
                    host=self._config['host'],
                    port=self._config['port'],
                    db=self._config['db'],
                    password=self._config['password'],
                    decode_responses=self._config['decode_responses'],
                    max_connections=self._config['max_connections'],
                    socket_timeout=self._config['socket_timeout'],
                    socket_connect_timeout=self._config['socket_connect_timeout']
                )
            
            # Create client using pool
            self._client = Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            
            self._logger.info(
                f"Redis connected to {self._config['host']}:{self._config['port']}, "
                f"db={self._config['db']}"
            )
            
        except Exception as e:
            self._logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    async def close(self) -> None:
        """Close Redis connection and cleanup resources"""
        if self._client:
            await self._client.close()
            self._client = None
            
        if self._pool:
            await self._pool.disconnect()
            self._pool = None
            
        self._logger.debug("Redis connection closed")
    
    async def health_check(self) -> bool:
        """Check if Redis connection is healthy"""
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except Exception as e:
            self._logger.error(f"Redis health check failed: {e}")
            return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.get_client()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

class CachedRedisProvider(RedisProviderService):
    """
    Redis provider with built-in caching strategies
    
    Extends the base Redis provider with common caching patterns.
    """
    
    def __init__(self, **kwargs):
        """Initialize with caching capabilities"""
        super().__init__(**kwargs)
        self._cache_prefix = kwargs.get('cache_prefix', 'cache:')
        
    async def get_cached(self, 
                        key: str, 
                        factory: callable,
                        ttl: int = 3600) -> Any:
        """
        Get value from cache or compute and store it
        
        Args:
            key: Cache key
            factory: Async callable to compute value if not cached
            ttl: Time to live in seconds
            
        Returns:
            Cached or computed value
        """
        client = await self.get_client()
        cache_key = f"{self._cache_prefix}{key}"
        
        # Try to get from cache
        cached = await client.get(cache_key)
        if cached is not None:
            return cached
            
        # Compute value
        value = await factory() if asyncio.iscoroutinefunction(factory) else factory()
        
        # Store in cache
        await client.set(cache_key, value, ex=ttl)
        
        return value
    
    async def invalidate_cache(self, pattern: str = "*") -> int:
        """
        Invalidate cache entries matching pattern
        
        Args:
            pattern: Redis key pattern (e.g., "user:*")
            
        Returns:
            Number of keys deleted
        """
        client = await self.get_client()
        cache_pattern = f"{self._cache_prefix}{pattern}"
        
        # Find matching keys
        keys = []
        async for key in client.scan_iter(match=cache_pattern):
            keys.append(key)
        
        # Delete keys
        if keys:
            return await client.delete(*keys)
        
        return 0