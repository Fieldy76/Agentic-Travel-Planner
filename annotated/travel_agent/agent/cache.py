import functools
import time
from typing import Dict, Any

class ToolCache:
    """Simple in-memory cache for tool calls."""
    
    def __init__(self, ttl_seconds: int = 300):
        self._cache: Dict[str, Any] = {}
        self._ttl = ttl_seconds
        
    def cached(self, func):
        """Decorator to cache function results based on arguments."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            key_parts = [func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            key = ":".join(key_parts)
            
            # Check cache
            if key in self._cache:
                timestamp, value = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    return value
            
            # Execute and cache
            result = func(*args, **kwargs)
            self._cache[key] = (time.time(), result)
            return result
            
        return wrapper

# Global cache instance
global_tool_cache = ToolCache()
