"""
Standardized exception handling for energy arbitrage system.
Provides consistent error handling patterns while maintaining fallback behaviors.
"""

import logging
import functools
from typing import Any, Dict, Optional, Callable, TypeVar, Union, Tuple
from datetime import datetime

_LOGGER = logging.getLogger(__name__)

F = TypeVar('F', bound=Callable[..., Any])

class ArbitrageError(Exception):
    """Base exception for all energy arbitrage errors."""
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None, 
                 original_error: Optional[Exception] = None):
        super().__init__(message)
        self.details = details or {}
        self.original_error = original_error
        self.timestamp = datetime.now()
    
    def __str__(self):
        if self.details:
            return f"{super().__str__()} | Details: {self.details}"
        return super().__str__()


class ConfigurationError(ArbitrageError):
    """Raised when configuration is invalid or missing."""
    pass


class SensorDataError(ArbitrageError):
    """Raised when sensor data is unavailable or invalid."""
    pass


class OptimizationError(ArbitrageError):
    """Raised when optimization calculations fail."""
    pass


class PlanningError(ArbitrageError):
    """Raised when strategic planning encounters errors."""
    pass


class ExecutionError(ArbitrageError):
    """Raised when command execution fails."""
    pass


def safe_execute(default_return: Any = None, 
                exception_types: Tuple[type, ...] = (Exception,),
                log_level: int = logging.WARNING,
                raise_on_error: bool = False) -> Callable[[F], F]:
    """
    Decorator for consistent error handling across the arbitrage system.
    
    Provides standardized error handling with fallback values while maintaining
    existing behavior patterns. Logs errors consistently and optionally raises
    custom exceptions.
    
    Args:
        default_return: Value to return if function fails (preserves fallback behavior)
        exception_types: Tuple of exception types to catch
        log_level: Logging level for caught exceptions
        raise_on_error: Whether to raise ArbitrageError after logging (for critical functions)
    
    Returns:
        Decorated function with error handling
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except exception_types as e:
                error_details = {
                    'function': func.__name__,
                    'module': func.__module__,
                    'args_count': len(args),
                    'kwargs_keys': list(kwargs.keys()) if kwargs else [],
                    'error_type': type(e).__name__,
                    'error_message': str(e)
                }
                
                _LOGGER.log(log_level, 
                           f"Error in {func.__name__}: {e}", 
                           extra={'error_details': error_details})
                
                if raise_on_error:
                    # Convert to appropriate ArbitrageError subtype
                    if 'config' in func.__name__.lower():
                        raise ConfigurationError(
                            f"Configuration error in {func.__name__}", 
                            error_details, e
                        ) from e
                    elif 'sensor' in func.__name__.lower() or 'data' in func.__name__.lower():
                        raise SensorDataError(
                            f"Sensor data error in {func.__name__}", 
                            error_details, e
                        ) from e
                    elif 'optim' in func.__name__.lower() or 'calculate' in func.__name__.lower():
                        raise OptimizationError(
                            f"Optimization error in {func.__name__}", 
                            error_details, e
                        ) from e
                    elif 'plan' in func.__name__.lower():
                        raise PlanningError(
                            f"Planning error in {func.__name__}", 
                            error_details, e
                        ) from e
                    elif 'execut' in func.__name__.lower() or 'command' in func.__name__.lower():
                        raise ExecutionError(
                            f"Execution error in {func.__name__}", 
                            error_details, e
                        ) from e
                    else:
                        raise ArbitrageError(
                            f"Error in {func.__name__}", 
                            error_details, e
                        ) from e
                
                # Return default value to maintain existing fallback behavior
                return default_return
        
        return wrapper
    return decorator


def log_performance(func: F) -> F:
    """
    Decorator to log performance metrics for optimization monitoring.
    
    Tracks execution time and provides performance insights without affecting
    functionality. Used for identifying optimization opportunities.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start_time = datetime.now()
        try:
            result = func(*args, **kwargs)
            duration = (datetime.now() - start_time).total_seconds()
            
            # Log performance for functions taking >100ms
            if duration > 0.1:
                _LOGGER.debug(f"Performance: {func.__name__} took {duration:.3f}s")
            
            return result
        except Exception as e:
            duration = (datetime.now() - start_time).total_seconds()
            _LOGGER.debug(f"Performance: {func.__name__} failed after {duration:.3f}s")
            raise
    
    return wrapper