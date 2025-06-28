"""
Fixed Adapter Factory Service Implementation

This version properly handles plugin loading with correct imports.
"""

from typing import Dict, Any, List, Optional
import logging
import importlib
import sys
from pathlib import Path
from app.core.di.interfaces import IAdapterFactory, IHTTPClientProvider, IConfigurationProvider
from app.core.adapters.base_adapter import BaseAdapter
from app.core.plugins.base_plugin import LLMAdapterPlugin

class AdapterFactoryService(IAdapterFactory):
    """
    Fixed implementation of IAdapterFactory
    
    This version:
    - Properly handles plugin imports
    - Creates adapters through plugin instances
    - Maintains backward compatibility
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
        self._plugin_directory = plugin_directory or Path("app/core/plugins")
        self._logger = logging.getLogger(__name__)
        self._adapter_registry: Dict[str, type] = {}
        self._plugin_registry: Dict[str, LLMAdapterPlugin] = {}
        
        # Register built-in adapters
        self._register_builtin_adapters()
        
        # Load plugins using import
        self._load_plugins()
    
    def _register_builtin_adapters(self) -> None:
        """Register built-in adapter types"""
        builtin_adapters = {
            'openai': 'app.core.adapters.openai_adapter.OpenAIAdapter',
            'claude': 'app.core.adapters.claude_adapter.ClaudeAdapter',
            'gemini': 'app.core.adapters.gemini_adapter.GeminiAdapter',
            'openrouter': 'app.core.adapters.openrouter_adapter.OpenRouterAdapter',
            'universal': 'app.core.adapters.universal_adapter.UniversalAdapter'
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
    
    def _load_plugins(self) -> None:
        """Load plugins using proper imports"""
        # Import known plugins directly to avoid dynamic loading issues
        plugin_modules = [
            'app.core.plugins.claude_plugin',
            'app.core.plugins.openrouter_plugin',
            'app.core.plugins.gemini_plugin',
            'app.core.plugins.ollama_plugin',
            'app.core.plugins.cli_plugin',
            'app.core.plugins.openai_plugin'
        ]
        
        for module_name in plugin_modules:
            try:
                # Import the plugin module
                module = importlib.import_module(module_name)
                
                # Find plugin classes
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, LLMAdapterPlugin) and 
                        attr is not LLMAdapterPlugin):
                        
                        # Create plugin instance
                        plugin_instance = attr()
                        plugin_name = plugin_instance.name
                        self._plugin_registry[plugin_name] = plugin_instance
                        self._logger.info(f"Loaded plugin: {plugin_name}")
                        
            except Exception as e:
                self._logger.warning(f"Failed to load plugin {module_name}: {e}")
    
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
        
        # Check if we should use a plugin
        adapter_service = config.get('adapter_service')
        if adapter_service and adapter_service in self._plugin_registry:
            # Use plugin to create adapter
            plugin = self._plugin_registry[adapter_service]
            
            # Check if plugin is available
            if not plugin.is_available(config):
                raise ValueError(f"Plugin {adapter_service} is not available (missing API key?)")
            
            # Create adapter through plugin
            adapter = plugin.create_adapter(config)
            self._logger.info(f"Created adapter for {model_name} using plugin: {adapter_service}")
            return adapter
        
        # Fallback to direct adapter creation
        adapter_type = config.get('adapter_type', config.get('model_type', 'universal'))
        
        # Get adapter class
        adapter_class = self._adapter_registry.get(adapter_type)
        if not adapter_class:
            # Try to use universal adapter as fallback
            self._logger.warning(f"Unknown adapter type '{adapter_type}', using universal adapter")
            adapter_class = self._adapter_registry.get('universal')
            if not adapter_class:
                raise ValueError(f"No adapter available for type: {adapter_type}")
        
        # Create adapter instance directly
        try:
            # Get HTTP client (some adapters might need it)
            http_client = await self._http_provider.get_client()
            
            # Try different constructor signatures
            try:
                # Try with all parameters
                adapter = adapter_class(
                    model_name=model_name,
                    config=config,
                    http_client=http_client
                )
            except TypeError:
                # Try without http_client
                try:
                    adapter = adapter_class(
                        model_name=model_name,
                        config=config
                    )
                except TypeError:
                    # Try with just config
                    adapter = adapter_class(config)
            
            self._logger.info(f"Created {adapter_type} adapter for model: {model_name}")
            return adapter
            
        except Exception as e:
            self._logger.error(f"Failed to create adapter for {model_name}: {e}")
            raise
    
    def get_available_adapters(self) -> List[str]:
        """Get list of available adapter types"""
        adapters = list(self._adapter_registry.keys())
        plugins = list(self._plugin_registry.keys())
        return sorted(set(adapters + plugins))
    
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