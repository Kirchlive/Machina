"""
Logger Service Implementation

Provides centralized logging with structured output and multiple handlers.
"""

import logging
import sys
from typing import Optional, Dict, Any
from pathlib import Path
from datetime import datetime
import json
from app.core.di.interfaces import ILogger

class LoggerService(ILogger):
    """
    Concrete implementation of ILogger
    
    Provides structured logging with:
    - Multiple output handlers
    - JSON formatting option
    - Log rotation support
    - Context injection
    """
    
    def __init__(self,
                 name: str = "llm_bridge",
                 level: str = "INFO",
                 log_file: Optional[Path] = None,
                 json_format: bool = False,
                 include_timestamp: bool = True):
        """
        Initialize the logger service
        
        Args:
            name: Logger name
            level: Logging level (DEBUG, INFO, WARNING, ERROR)
            log_file: Optional file path for file logging
            json_format: Whether to use JSON formatting
            include_timestamp: Whether to include timestamps
        """
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.upper()))
        self._json_format = json_format
        self._context: Dict[str, Any] = {}
        
        # Remove existing handlers to avoid duplicates
        self._logger.handlers.clear()
        
        # Create formatter
        if json_format:
            formatter = JsonFormatter(include_timestamp=include_timestamp)
        else:
            if include_timestamp:
                format_str = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            else:
                format_str = '%(name)s - %(levelname)s - %(message)s'
            formatter = logging.Formatter(format_str)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self._logger.addHandler(console_handler)
        
        # File handler if specified
        if log_file:
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            self._logger.addHandler(file_handler)
    
    def _log(self, level: int, message: str, **kwargs) -> None:
        """Internal logging method with context injection"""
        extra = {**self._context, **kwargs}
        self._logger.log(level, message, extra=extra)
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self._log(logging.ERROR, message, **kwargs)
    
    def exception(self, message: str, exc_info=True, **kwargs) -> None:
        """Log exception with traceback"""
        self._logger.exception(message, exc_info=exc_info, extra={**self._context, **kwargs})
    
    def set_context(self, **kwargs) -> None:
        """Set persistent context for all future logs"""
        self._context.update(kwargs)
    
    def clear_context(self) -> None:
        """Clear persistent context"""
        self._context.clear()
    
    def get_logger(self) -> logging.Logger:
        """Get underlying logger instance (for compatibility)"""
        return self._logger

class JsonFormatter(logging.Formatter):
    """JSON log formatter for structured logging"""
    
    def __init__(self, include_timestamp: bool = True):
        """Initialize JSON formatter"""
        super().__init__()
        self._include_timestamp = include_timestamp
    
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON"""
        log_data = {
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        }
        
        if self._include_timestamp:
            log_data['timestamp'] = datetime.utcfromtimestamp(record.created).isoformat()
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ['name', 'msg', 'args', 'created', 'filename', 
                          'funcName', 'levelname', 'levelno', 'lineno', 
                          'module', 'msecs', 'pathname', 'process', 
                          'processName', 'relativeCreated', 'thread', 
                          'threadName', 'getMessage']:
                log_data[key] = value
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data)

class MultiLoggerService(LoggerService):
    """
    Logger service with multiple named loggers
    
    Useful for separating logs by component or module.
    """
    
    def __init__(self, base_name: str = "llm_bridge", **kwargs):
        """Initialize multi-logger service"""
        super().__init__(name=base_name, **kwargs)
        self._loggers: Dict[str, logging.Logger] = {
            'main': self._logger
        }
        self._base_config = kwargs
    
    def get_component_logger(self, component: str) -> ILogger:
        """
        Get a logger for a specific component
        
        Args:
            component: Component name
            
        Returns:
            Logger instance for the component
        """
        logger_name = f"{self._logger.name}.{component}"
        
        if component not in self._loggers:
            # Create new logger service for component
            component_logger = LoggerService(
                name=logger_name,
                **self._base_config
            )
            self._loggers[component] = component_logger.get_logger()
            
            return component_logger
        
        # Return wrapper for existing logger
        return LoggerWrapper(self._loggers[component])

class LoggerWrapper(ILogger):
    """Wrapper to make logging.Logger compatible with ILogger interface"""
    
    def __init__(self, logger: logging.Logger):
        """Initialize wrapper"""
        self._logger = logger
    
    def debug(self, message: str, **kwargs) -> None:
        """Log debug message"""
        self._logger.debug(message, extra=kwargs)
    
    def info(self, message: str, **kwargs) -> None:
        """Log info message"""
        self._logger.info(message, extra=kwargs)
    
    def warning(self, message: str, **kwargs) -> None:
        """Log warning message"""
        self._logger.warning(message, extra=kwargs)
    
    def error(self, message: str, **kwargs) -> None:
        """Log error message"""
        self._logger.error(message, extra=kwargs)