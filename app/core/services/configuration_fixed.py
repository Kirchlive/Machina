"""
Fixed Configuration Service Implementation

This version handles both nested models structure and direct model definitions.
"""

from typing import Any, Dict, Optional, List
import os
import yaml
from pathlib import Path
import logging
from app.core.di.interfaces import IConfigurationProvider

class ConfigurationService(IConfigurationProvider):
    """
    Fixed implementation of IConfigurationProvider
    
    This version properly handles registry.yaml where models
    are defined directly at root level, not under a 'models' key.
    """
    
    def __init__(self, 
                 config_path: Optional[Path] = None,
                 env_prefix: str = "LLM_BRIDGE_"):
        """
        Initialize the configuration service
        
        Args:
            config_path: Path to the main configuration file
            env_prefix: Prefix for environment variables
        """
        self._config: Dict[str, Any] = {}
        self._env_prefix = env_prefix
        self._logger = logging.getLogger(__name__)
        
        # Load configuration in order of precedence
        if config_path and config_path.exists():
            self._load_from_file(config_path)
        else:
            # Try default locations
            self._load_default_configs()
            
        # Environment variables override file configs
        self._load_from_env()
        
        self._logger.info(f"Configuration loaded with {len(self._config)} top-level keys")
    
    def _load_default_configs(self) -> None:
        """Load from default configuration locations"""
        default_paths = [
            Path("config/models.yaml"),
            Path("config/registry.yaml"),
            Path("registry.yaml"),  # Legacy location
        ]
        
        for path in default_paths:
            if path.exists():
                self._logger.info(f"Loading configuration from {path}")
                self._load_from_file(path)
                break
    
    def _load_from_file(self, path: Path) -> None:
        """Load configuration from a YAML file"""
        try:
            with open(path, 'r') as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    self._config.update(data)
                    self._logger.debug(f"Loaded {len(data)} keys from {path}")
        except Exception as e:
            self._logger.error(f"Failed to load config from {path}: {e}")
    
    def _load_from_env(self) -> None:
        """Load configuration from environment variables"""
        env_count = 0
        for key, value in os.environ.items():
            if key.startswith(self._env_prefix):
                config_key = key[len(self._env_prefix):].lower()
                # Convert nested keys (e.g., MODEL__NAME to model.name)
                config_key = config_key.replace('__', '.')
                
                # Try to parse as YAML for complex values
                try:
                    parsed_value = yaml.safe_load(value)
                    self._set_nested(config_key, parsed_value)
                    env_count += 1
                except:
                    # If parsing fails, use as string
                    self._set_nested(config_key, value)
                    env_count += 1
        
        if env_count > 0:
            self._logger.debug(f"Loaded {env_count} values from environment variables")
    
    def _set_nested(self, key: str, value: Any) -> None:
        """Set a nested configuration value using dot notation"""
        parts = key.split('.')
        current = self._config
        
        for part in parts[:-1]:
            if part not in current:
                current[part] = {}
            current = current[part]
        
        current[parts[-1]] = value
    
    def _get_nested(self, key: str, default: Any = None) -> Any:
        """Get a nested configuration value using dot notation"""
        parts = key.split('.')
        current = self._config
        
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        
        return current
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key (supports dot notation)"""
        return self._get_nested(key, default)
    
    def get_model_config(self, model_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific model"""
        # First check if there's a 'models' section
        models = self.get('models')
        if models and isinstance(models, dict):
            return models.get(model_name)
        
        # If no 'models' section, check root level (registry.yaml style)
        return self._config.get(model_name) if self._is_model_config(model_name) else None
    
    def get_all_models(self) -> Dict[str, Dict[str, Any]]:
        """Get all model configurations"""
        # First check if there's a 'models' section
        models = self.get('models')
        if models and isinstance(models, dict):
            return models
        
        # Otherwise, extract models from root level
        # Models are entries that have model-specific keys
        result = {}
        for key, value in self._config.items():
            if self._is_model_config(key, value):
                result[key] = value
        
        return result
    
    def _is_model_config(self, key: str, value: Any = None) -> bool:
        """Check if a config entry is a model configuration"""
        # Skip private keys and known non-model sections
        if key.startswith('_') or key in ['agents', 'crews', 'mission_templates']:
            return False
        
        # If we have the value, check for model-specific keys
        if value is None:
            value = self._config.get(key, {})
        
        if not isinstance(value, dict):
            return False
        
        # Check for model-specific keys
        model_keys = {'adapter_service', 'model_name_direct', 'model_name_openrouter', 
                      'provider', 'platform', 'context_window', 'capabilities'}
        return any(k in value for k in model_keys)
    
    def get_redis_config(self) -> Dict[str, Any]:
        """Get Redis configuration"""
        return {
            'host': self.get('redis.host', 'localhost'),
            'port': self.get('redis.port', 6379),
            'db': self.get('redis.db', 0),
            'password': self.get('redis.password'),
            'decode_responses': self.get('redis.decode_responses', True)
        }
    
    def get_api_config(self) -> Dict[str, Any]:
        """Get API server configuration"""
        return {
            'host': self.get('api.host', '0.0.0.0'),
            'port': self.get('api.port', 8000),
            'debug': self.get('api.debug', False),
            'cors_origins': self.get('api.cors_origins', ['*'])
        }
    
    def reload(self, config_path: Optional[Path] = None) -> None:
        """Reload configuration from files and environment"""
        self._config.clear()
        
        if config_path:
            self._load_from_file(config_path)
        else:
            self._load_default_configs()
            
        self._load_from_env()
        self._logger.info("Configuration reloaded")