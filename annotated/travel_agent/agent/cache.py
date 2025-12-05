"""
================================================================================
TOOL CACHE - Simple Caching Layer for Tool Results
================================================================================

This module provides a caching mechanism for tool function calls to reduce
redundant API requests and improve response times. When a tool is called
with the same arguments within the TTL (time-to-live), the cached result
is returned instead of executing the tool again.

Use Cases:
----------
1. Weather Forecasts: Weather doesn't change minute-to-minute, so caching
   for 5 minutes is perfectly acceptable.

2. Flight Searches: Flight prices can change, but caching for a few minutes
   reduces load on the flight API during a conversation.

3. Any Idempotent Tool: If calling a tool with the same arguments always
   returns the same result, caching is safe.

NOT Suitable For:
-----------------
- Booking operations (side effects)
- Payment processing (side effects)  
- Current time (changes constantly)

Architecture:
-------------
    ┌─────────────────────────────────────────────────────┐
    │                    Tool Call                        │
    └────────────────────┬────────────────────────────────┘
                         │
                         ▼
    ┌─────────────────────────────────────────────────────┐
    │              Generate Cache Key                     │
    │         (function_name + serialized args)           │
    └────────────────────┬────────────────────────────────┘
                         │
              ┌──────────┴──────────┐
              ▼                     ▼
         Cache HIT              Cache MISS
         (within TTL)           (expired or new)
              │                     │
              │                     ▼
              │        ┌─────────────────────────┐
              │        │   Execute Real Tool     │
              │        └───────────┬─────────────┘
              │                    │
              │                    ▼
              │        ┌─────────────────────────┐
              │        │   Store in Cache        │
              │        │   (with timestamp)      │
              │        └───────────┬─────────────┘
              │                    │
              └────────┬───────────┘
                       ▼
    ┌─────────────────────────────────────────────────────┐
    │                  Return Result                      │
    └─────────────────────────────────────────────────────┘

Cache Key Format:
-----------------
    "function_name:arg1:arg2:kwarg1=value1:kwarg2=value2"

Example:
    "get_forecast:London:2024-03-15" -> cached weather data

Limitations:
------------
1. In-Memory Only: Cache is lost on process restart
2. Single Process: Not shared across multiple workers
3. No Size Limit: Could grow indefinitely for many unique calls
4. Sync Only: The decorator only works with synchronous functions

For production, consider:
- Redis for distributed caching
- LRU eviction to limit memory usage
- Async-compatible decorators

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

import functools  # For creating decorators that preserve function metadata
import time       # For timestamp-based TTL expiration
from typing import Dict, Any  # Type hints

# =============================================================================
# TOOL CACHE CLASS
# =============================================================================

class ToolCache:
    """
    Simple in-memory cache for tool call results with TTL expiration.
    
    This class provides a decorator-based caching mechanism. When applied
    to a function, subsequent calls with the same arguments will return
    the cached result if it hasn't expired.
    
    Attributes:
        _cache (Dict[str, Any]): The internal cache storage
                                 Keys are cache keys, values are (timestamp, result) tuples
        _ttl (int): Time-to-live in seconds for cached entries
    
    Example:
        >>> cache = ToolCache(ttl_seconds=60)  # 1 minute cache
        >>> 
        >>> @cache.cached
        ... def expensive_api_call(arg1, arg2):
        ...     # This only runs once per unique (arg1, arg2) within 60 seconds
        ...     return fetch_from_api(arg1, arg2)
        >>> 
        >>> result1 = expensive_api_call("a", "b")  # Calls API
        >>> result2 = expensive_api_call("a", "b")  # Returns cached value
        >>> result3 = expensive_api_call("a", "c")  # Calls API (different args)
    
    Thread Safety:
        This implementation is NOT thread-safe. For multi-threaded use,
        wrap cache access in a lock or use threading.local().
    """
    
    def __init__(self, ttl_seconds: int = 300):
        """
        Initialize the cache with a specified TTL.
        
        Args:
            ttl_seconds: How long cached values remain valid, in seconds.
                        Default is 300 seconds (5 minutes).
        
        Example:
            >>> short_cache = ToolCache(ttl_seconds=60)    # 1 minute
            >>> long_cache = ToolCache(ttl_seconds=3600)   # 1 hour
        """
        self._cache: Dict[str, Any] = {}  # Storage for cached values
        self._ttl = ttl_seconds           # Time-to-live in seconds
        
    def cached(self, func):
        """
        Decorator that caches function results based on arguments.
        
        When applied to a function, this decorator:
        1. Generates a cache key from the function name and all arguments
        2. Checks if a valid (non-expired) cached value exists
        3. Returns the cached value if valid
        4. Otherwise, executes the function and caches the result
        
        Args:
            func: The function to wrap with caching
        
        Returns:
            A wrapper function that implements caching
        
        Usage:
            @tool_cache.cached
            def my_function(arg1, arg2):
                return expensive_operation(arg1, arg2)
        
        Note:
            - Arguments must be serializable to strings
            - Keyword arguments are sorted for consistent key generation
            - The function's return value must be cacheable (any type works)
        
        Limitations:
            - Does not work with async functions (use asyncio-compatible cache)
            - Arguments with the same string representation are considered equal
        """
        @functools.wraps(func)  # Preserve original function metadata (__name__, __doc__, etc.)
        def wrapper(*args, **kwargs):
            # -----------------------------------------------------------------
            # Step 1: Generate a unique cache key
            # -----------------------------------------------------------------
            # The key format is: function_name:arg1:arg2:...:key1=val1:key2=val2:...
            # This ensures different calls get different keys
            
            key_parts = [func.__name__]  # Start with function name
            
            # Add positional arguments
            key_parts.extend(str(arg) for arg in args)
            
            # Add keyword arguments (sorted for consistency)
            # Sorting ensures {"a": 1, "b": 2} and {"b": 2, "a": 1} get the same key
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            
            # Join all parts with colons
            key = ":".join(key_parts)
            
            # -----------------------------------------------------------------
            # Step 2: Check cache for valid (non-expired) entry
            # -----------------------------------------------------------------
            if key in self._cache:
                timestamp, value = self._cache[key]
                
                # Check if the cached value is still within TTL
                if time.time() - timestamp < self._ttl:
                    # Cache hit! Return the cached value
                    return value
                # Cache expired, will fall through to execute function
            
            # -----------------------------------------------------------------
            # Step 3: Execute function and cache the result
            # -----------------------------------------------------------------
            # Cache miss or expired - execute the actual function
            result = func(*args, **kwargs)
            
            # Store result with current timestamp
            self._cache[key] = (time.time(), result)
            
            return result
            
        return wrapper

# =============================================================================
# GLOBAL CACHE INSTANCE
# =============================================================================

# Create a global cache instance with default 5-minute TTL.
# This is used by tools that want to cache their results.
#
# Usage in other modules:
#     from travel_agent.agent.cache import global_tool_cache
#     
#     @global_tool_cache.cached
#     def my_tool_function(...):
#         ...
#
# The global instance allows sharing cache across all tool calls
# within the same process.

global_tool_cache = ToolCache()
