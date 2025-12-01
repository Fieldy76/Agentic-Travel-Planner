# Import functools for the wraps decorator
import functools
# Import time to track cache expiration
import time
# Import type hints
from typing import Dict, Any

class ToolCache:
    """
    Simple in-memory cache for tool calls with TTL (Time To Live).
    
    This cache helps improve performance by:
    - Avoiding redundant API calls for identical requests
    - Reducing costs (many APIs charge per request)
    - Decreasing latency for repeated queries
    
    Use cases:
    - Weather queries (weather doesn't change every second)
    - Flight searches (results are relatively stable for a few minutes)
    - Static data lookups
    """
    
    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize the cache.
        
        Args:
            ttl_seconds: How long cached values remain valid (default: 5 minutes)
        """
        # Dictionary to store cached results
        # Key: string representing function + arguments
        # Value: tuple of (timestamp, result)
        self._cache: Dict[str, Any] = {}
        # Time-to-live in seconds
        self._ttl = ttl_seconds
        
    def cached(self, func):
        """
        Decorator to cache function results based on arguments.
        
        Usage:
            @cache.cached
            def expensive_function(arg1, arg2):
                # ... expensive operation ...
        
        Args:
            func: The function to wrap with caching
            
        Returns:
            Wrapped function that checks cache before executing
        """
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # STEP 1: Generate a unique cache key from function name and arguments
            # Start with the function name
            key_parts = [func.__name__]
            # Add all positional arguments as strings
            key_parts.extend(str(arg) for arg in args)
            # Add all keyword arguments (sorted for consistency)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            # Join with colons to create the key
            # Example: "search_flights:JFK:LAX:2023-12-25"
            key = ":".join(key_parts)
            
            # STEP 2: Check if we have a cached result
            if key in self._cache:
                timestamp, value = self._cache[key]
                # Check if the cached value is still fresh (not expired)
                if time.time() - timestamp < self._ttl:
                    # Cache hit! Return the cached value without executing the function
                    return value
            
            # STEP 3: Cache miss or expired - execute the function
            result = func(*args, **kwargs)
            
            # STEP 4: Store the result in cache with current timestamp
            self._cache[key] = (time.time(), result)
            
            # Return the freshly computed result
            return result
            
        # Return the wrapped function
        return wrapper

# Global cache instance
# This is shared across all tool modules
# Using a single instance ensures consistent caching behavior
# Default TTL: 5 minutes (300 seconds)
global_tool_cache = ToolCache()
