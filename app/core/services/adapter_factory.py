"""
Adapter Factory Service Implementation

Creates and manages LLM adapter instances based on configuration.
"""

from typing import Dict, Any, List, Optional
import logging
import importlib
import os
from pathlib import Path
from app.core.di.interfaces import IAdapterFactory, IHTTPClientProvider, IConfigurationProvider
from app.core.adapters.base_adapter import BaseAdapter

class AdapterFactoryService(IAdapterFactory):
    """
    Concrete implementation of IAdapterFactory
    
    Responsible for:
    - Dynamic adapter loading
    - Plugin discovery
    - Adapter instantiation with proper dependencies
    """
    
    def __init__(self,
                 http_client_provider: IHTTPClientProvider,
                 config_provider: IConfigurationProvider,
                 plugin_directory: Optional[Path] = None):
        """
        Initialize the adapter factory
        
        Args:
            http_client_provider: HTTP client provider for adapters
            config_provider: Configuration provider
            plugin_directory: Optional directory for plugin adapters
        """
        self._http_provider = http_client_provider
        self._config_provider = config_provider
        self._plugin_directory = plugin_directory or Path("llm_bridge/plugins")
        self._logger = logging.getLogger(__name__)
        self._adapter_registry: Dict[str, type] = {}
        
        # Register built-in adapters
        self._register_builtin_adapters()
        
        # Discover plugin adapters
        if self._plugin_directory.exists():
            self._discover_plugins()
    
    def _register_builtin_adapters(self) -> None:
        """Register built-in adapter types"""
        builtin_adapters = {
            'openai': 'llm_bridge.adapters.openai_adapter.OpenAIAdapter',
            'claude': 'llm_bridge.adapters.claude_adapter.ClaudeAdapter',
            'gemini': 'llm_bridge.adapters.gemini_adapter.GeminiAdapter',
            'openrouter': 'llm_bridge.adapters.openrouter_adapter.OpenRouterAdapter',
            'universal': 'llm_bridge.adapters.universal_adapter.UniversalAdapter'
        }
        
        for name, class_path in builtin_adapters.items():
            try:
                module_path, class_name = class_path.rsplit('.', 1)
                module = importlib.import_module(module_path)
                adapter_class = getattr(module, class_name)
                self._adapter_registry[name] = adapter_class
                self._logger.debug(f"Registered built-in adapter: {name}")
            except Exception as e:
                self._logger.warning(f"Failed to register adapter {name}: {e}")
    
    def _discover_plugins(self) -> None:
        """Discover and register plugin adapters"""
        for file in self._plugin_directory.glob("*_plugin.py"):
            if file.name.startswith('__'):
                continue
                
            try:
                # Import plugin module
                module_name = file.stem
                spec = importlib.util.spec_from_file_location(module_name, file)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    # Look for adapter classes
                    for attr_name in dir(module):
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseAdapter) and 
                            attr is not BaseAdapter):
                            
                            adapter_name = attr_name.lower().replace('adapter', '')
                            self._adapter_registry[adapter_name] = attr
                            self._logger.info(f"Discovered plugin adapter: {adapter_name}")
                            
            except Exception as e:
                self._logger.error(f"Failed to load plugin {file}: {e}")
    
    async def create_adapter(self, model_name: str, config: Optional[Dict[str, Any]] = None) -> BaseAdapter:
        """
        Create an adapter instance for the specified model
        
        Args:
            model_name: Name of the model
            config: Optional configuration override
            
        Returns:
            Configured adapter instance
        """
        # Get configuration if not provided
        if config is None:
            config = self._config_provider.get_model_config(model_name)
            if not config:
                raise ValueError(f"No configuration found for model: {model_name}")
        
        # Determine adapter type
        adapter_type = config.get('adapter_type', config.get('model_type', 'universal'))
        
        # Get adapter class
        adapter_class = self._adapter_registry.get(adapter_type)
        if not adapter_class:
            # Try to use universal adapter as fallback
            self._logger.warning(f"Unknown adapter type '{adapter_type}', using universal adapter")
            adapter_class = self._adapter_registry.get('universal')
            if not adapter_class:
                raise ValueError(f"No adapter available for type: {adapter_type}")
        
        # Get HTTP client
        http_client = await self._http_provider.get_client()
        
        # Create adapter instance
        try:
            adapter = adapter_class(
                model_name=model_name,
                config=config,
                http_client=http_client
            )
            
            self._logger.info(f"Created {adapter_type} adapter for model: {model_name}")
            return adapter
            
        except Exception as e:
            self._logger.error(f"Failed to create adapter for {model_name}: {e}")
            raise
    
    def get_available_adapters(self) -> List[str]:
        """Get list of available adapter types"""
        return list(self._adapter_registry.keys())
    
    def register_adapter(self, name: str, adapter_class: type) -> None:
        """
        Register a custom adapter type
        
        Args:
            name: Adapter type name
            adapter_class: Adapter class
        """
        if not issubclass(adapter_class, BaseAdapter):
            raise ValueError(f"{adapter_class} must inherit from BaseAdapter")
            
        self._adapter_registry[name] = adapter_class
        self._logger.info(f"Registered custom adapter: {name}")

class CachedAdapterFactory(AdapterFactoryService):
    """
    Adapter factory with instance caching
    
    Reuses adapter instances for the same model to reduce overhead.
    """
    
    def __init__(self, **kwargs):
        """Initialize with caching"""
        super().__init__(**kwargs)
        self._adapter_cache: Dict[str, BaseAdapter] = {}
    
    async def create_adapter(self, model_name: str, config: Optional[Dict[str, Any]] = None) -> BaseAdapter:
        """Create or retrieve cached adapter"""
        # Check cache first
        if model_name in self._adapter_cache:
            self._logger.debug(f"Returning cached adapter for: {model_name}")
            return self._adapter_cache[model_name]
        
        # Create new adapter
        adapter = await super().create_adapter(model_name, config)
        
        # Cache it
        self._adapter_cache[model_name] = adapter
        
        return adapter
    
    def clear_cache(self) -> None:
        """Clear adapter cache"""
        self._adapter_cache.clear()
        self._logger.info("Adapter cache cleared")