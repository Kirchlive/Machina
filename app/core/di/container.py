"""
Service Container for Dependency Injection

This container manages the lifecycle of services and their dependencies,
supporting singleton, transient, and scoped lifetimes.
"""

from typing import Dict, Type, Callable, Any, TypeVar, Optional, Union
from enum import Enum
import asyncio
import inspect
from functools import wraps

T = TypeVar('T')

class ServiceLifetime(Enum):
    """Service lifetime options"""
    SINGLETON = "singleton"
    TRANSIENT = "transient"
    SCOPED = "scoped"

class ServiceDescriptor:
    """Describes a service registration"""
    
    def __init__(self, 
                 service_type: Type,
                 factory: Callable,
                 lifetime: ServiceLifetime):
        self.service_type = service_type
        self.factory = factory
        self.lifetime = lifetime

class ServiceContainer:
    """
    Dependency Injection Container
    
    Manages service registration and resolution with support for:
    - Singleton: One instance for the entire application lifetime
    - Transient: New instance for each resolution
    - Scoped: One instance per scope (e.g., per request)
    """
    
    def __init__(self):
        self._services: Dict[Type, ServiceDescriptor] = {}
        self._singletons: Dict[Type, Any] = {}
        self._scoped: Dict[Type, Any] = {}
        self._resolving: set = set()  # Track circular dependencies
        
    def register_singleton(self, 
                         service_type: Type[T], 
                         factory: Optional[Callable[['ServiceContainer'], T]] = None,
                         instance: Optional[T] = None) -> None:
        """
        Register a singleton service
        
        Args:
            service_type: The interface/type to register
            factory: Factory function to create the service
            instance: Pre-created instance (if provided, factory is ignored)
        """
        if instance is not None:
            self._singletons[service_type] = instance
            self._services[service_type] = ServiceDescriptor(
                service_type, lambda _: instance, ServiceLifetime.SINGLETON
            )
        elif factory is not None:
            self._services[service_type] = ServiceDescriptor(
                service_type, factory, ServiceLifetime.SINGLETON
            )
        else:
            raise ValueError("Either factory or instance must be provided")
            
    def register_transient(self, 
                          service_type: Type[T], 
                          factory: Callable[['ServiceContainer'], T]) -> None:
        """Register a transient service"""
        self._services[service_type] = ServiceDescriptor(
            service_type, factory, ServiceLifetime.TRANSIENT
        )
        
    def register_scoped(self, 
                       service_type: Type[T], 
                       factory: Callable[['ServiceContainer'], T]) -> None:
        """Register a scoped service"""
        self._services[service_type] = ServiceDescriptor(
            service_type, factory, ServiceLifetime.SCOPED
        )
    
    async def resolve(self, service_type: Type[T]) -> T:
        """
        Resolve a service asynchronously
        
        Args:
            service_type: The interface/type to resolve
            
        Returns:
            The resolved service instance
            
        Raises:
            ValueError: If service is not registered
            RuntimeError: If circular dependency detected
        """
        # Check for circular dependencies
        if service_type in self._resolving:
            raise RuntimeError(f"Circular dependency detected for {service_type}")
            
        if service_type not in self._services:
            raise ValueError(f"Service {service_type} not registered")
            
        descriptor = self._services[service_type]
        
        try:
            self._resolving.add(service_type)
            
            if descriptor.lifetime == ServiceLifetime.SINGLETON:
                if service_type not in self._singletons:
                    instance = await self._create_instance(descriptor.factory)
                    self._singletons[service_type] = instance
                return self._singletons[service_type]
                
            elif descriptor.lifetime == ServiceLifetime.TRANSIENT:
                return await self._create_instance(descriptor.factory)
                
            elif descriptor.lifetime == ServiceLifetime.SCOPED:
                if service_type not in self._scoped:
                    instance = await self._create_instance(descriptor.factory)
                    self._scoped[service_type] = instance
                return self._scoped[service_type]
                
        finally:
            self._resolving.remove(service_type)
    
    async def _create_instance(self, factory: Callable) -> Any:
        """Create an instance using the factory"""
        # Check if factory expects the container as parameter
        sig = inspect.signature(factory)
        if len(sig.parameters) > 0:
            instance = factory(self)
        else:
            instance = factory()
            
        # Handle async factories
        if asyncio.iscoroutine(instance):
            instance = await instance
            
        return instance
    
    def resolve_sync(self, service_type: Type[T]) -> T:
        """
        Resolve a service synchronously (for non-async contexts)
        
        Note: This will fail if the factory is async
        """
        if service_type not in self._services:
            raise ValueError(f"Service {service_type} not registered")
            
        descriptor = self._services[service_type]
        
        if descriptor.lifetime == ServiceLifetime.SINGLETON:
            if service_type in self._singletons:
                return self._singletons[service_type]
                
        # For sync resolution, we can't handle async factories
        raise RuntimeError(
            f"Cannot resolve {service_type} synchronously. Use await resolve() instead."
        )
    
    def clear_scoped(self) -> None:
        """Clear all scoped services (typically called at the end of a request)"""
        self._scoped.clear()
    
    async def dispose(self) -> None:
        """
        Dispose of all services that implement IDisposable or have close/dispose methods
        """
        all_instances = list(self._singletons.values()) + list(self._scoped.values())
        
        for instance in all_instances:
            # Check for various dispose method names
            for method_name in ['dispose', 'close', 'shutdown', 'cleanup']:
                if hasattr(instance, method_name):
                    method = getattr(instance, method_name)
                    if callable(method):
                        result = method()
                        if asyncio.iscoroutine(result):
                            await result
                        break
    
    def create_scope(self) -> 'ServiceScope':
        """Create a new service scope"""
        return ServiceScope(self)

class ServiceScope:
    """
    Represents a service scope for scoped lifetime services
    """
    
    def __init__(self, container: ServiceContainer):
        self._container = container
        self._original_scoped = container._scoped.copy()
    
    async def __aenter__(self):
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Clear scoped services created in this scope
        self._container.clear_scoped()
        # Restore original scoped services
        self._container._scoped = self._original_scoped
    
    async def resolve(self, service_type: Type[T]) -> T:
        """Resolve a service within this scope"""
        return await self._container.resolve(service_type)

# Decorator for auto-wiring dependencies
def injectable(cls):
    """
    Decorator to mark a class as injectable with automatic dependency resolution
    """
    original_init = cls.__init__
    
    @wraps(original_init)
    def new_init(self, container: ServiceContainer, *args, **kwargs):
        # Auto-resolve dependencies based on type hints
        sig = inspect.signature(original_init)
        resolved_kwargs = {}
        
        for param_name, param in sig.parameters.items():
            if param_name == 'self':
                continue
                
            if param.annotation != param.empty and param_name not in kwargs:
                # Try to resolve the dependency
                try:
                    resolved_kwargs[param_name] = container.resolve_sync(param.annotation)
                except:
                    # If sync resolution fails, skip (will be handled by factory)
                    pass
        
        # Merge resolved dependencies with provided kwargs
        kwargs.update(resolved_kwargs)
        original_init(self, *args, **kwargs)
    
    cls.__init__ = new_init
    return cls