"""
================================================================================
AGENT MEMORY - Conversation History Management
================================================================================

This module provides abstractions for managing agent conversation memory.
Memory is essential for maintaining context across multiple turns of 
conversation, allowing the LLM to reference previous messages and tool calls.

Design Pattern: Strategy Pattern
---------------------------------
The AgentMemory abstract base class defines the interface, while concrete
implementations (like InMemoryMemory) provide specific storage strategies.
This allows easy swapping of storage backends without changing the orchestrator.

Memory Use Cases:
-----------------
1. Short-term Conversation: InMemoryMemory (implemented here)
   - Stores messages in a simple list
   - Lost when the process restarts
   - Perfect for single-session interactions

2. Long-term Persistence: Could be implemented as:
   - RedisMemory: Store in Redis for fast access across processes
   - PostgresMemory: Store in database for historical analysis
   - FileMemory: Store in JSON files for simple persistence

Message Format:
---------------
Messages follow a standard format compatible with all LLM providers:

    # User message
    {"role": "user", "content": "Hello!"}
    
    # User message with file attachment
    {"role": "user", "content": "What's in this image?", "files": [...]}
    
    # Assistant response
    {"role": "assistant", "content": "How can I help?"}
    
    # Assistant response with tool calls
    {
        "role": "assistant",
        "content": "I'll search for flights...",
        "tool_calls": [{"id": "tc_1", "name": "search_flights", "arguments": {...}}]
    }
    
    # Tool result
    {"role": "tool", "tool_call_id": "tc_1", "name": "search_flights", "content": "[...]"}

Author: Agentic Travel Planner Team
================================================================================
"""

# =============================================================================
# IMPORTS
# =============================================================================

from abc import ABC, abstractmethod          # Abstract base class support
from typing import List, Dict, Any           # Type hints

# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class AgentMemory(ABC):
    """
    Abstract base class for agent memory implementations.
    
    This class defines the interface that all memory implementations must
    follow. The orchestrator uses this interface, so any conforming 
    implementation can be used.
    
    The interface is intentionally minimal to support various storage backends:
    - In-memory lists
    - Redis/Memcached for distributed caching
    - SQL databases for persistence
    - Vector databases for semantic search
    
    Methods:
        add_message: Store a new message
        get_messages: Retrieve all messages
        clear: Reset the memory
    
    Example Implementation:
        class RedisMemory(AgentMemory):
            def __init__(self, redis_client, session_id):
                self.redis = redis_client
                self.key = f"chat:{session_id}"
            
            def add_message(self, message):
                self.redis.rpush(self.key, json.dumps(message))
            
            def get_messages(self):
                return [json.loads(m) for m in self.redis.lrange(self.key, 0, -1)]
            
            def clear(self):
                self.redis.delete(self.key)
    """
    
    @abstractmethod
    def add_message(self, message: Dict[str, Any]):
        """
        Add a message to the conversation history.
        
        Args:
            message: A message dictionary containing at minimum:
                - role: "user", "assistant", "system", or "tool"
                - content: The message text (may be None for tool-only messages)
                
                Optional fields:
                - files: List of file attachments for user messages
                - tool_calls: List of tool calls for assistant messages
                - tool_call_id: ID linking to the tool call (for tool messages)
                - name: Tool name (for tool messages)
        
        Example:
            >>> memory.add_message({"role": "user", "content": "Hello!"})
            >>> memory.add_message({
            ...     "role": "assistant",
            ...     "content": "I'll search for flights.",
            ...     "tool_calls": [{"id": "1", "name": "search_flights", "arguments": {}}]
            ... })
        """
        pass
        
    @abstractmethod
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Retrieve all messages from the conversation history.
        
        Returns:
            List of message dictionaries in chronological order.
            The list may be empty if no messages have been added.
        
        Note:
            This method returns references to internal data in InMemoryMemory.
            Callers should not modify the returned list directly.
        
        Example:
            >>> messages = memory.get_messages()
            >>> for msg in messages:
            ...     print(f"{msg['role']}: {msg['content']}")
        """
        pass
        
    @abstractmethod
    def clear(self):
        """
        Clear all messages from the conversation history.
        
        This resets the memory to its initial empty state. Useful for:
        - Starting a new conversation
        - Testing and debugging
        - Managing memory limits
        
        Warning:
            This operation is irreversible. In production, consider
            archiving messages before clearing if needed for analytics.
        
        Example:
            >>> memory.add_message({"role": "user", "content": "Hello!"})
            >>> len(memory.get_messages())
            1
            >>> memory.clear()
            >>> len(memory.get_messages())
            0
        """
        pass

# =============================================================================
# IN-MEMORY IMPLEMENTATION
# =============================================================================

class InMemoryMemory(AgentMemory):
    """
    Simple in-memory storage for agent messages.
    
    This is the default memory implementation, suitable for:
    - Single-user web sessions (stateless API with session per request)
    - CLI usage where persistence isn't needed
    - Development and testing
    
    Limitations:
    - Messages are lost when the process restarts
    - No limit on message count (could cause memory issues for long sessions)
    - Not suitable for multi-process deployments without sticky sessions
    
    For production web deployments with multiple workers or serverless
    functions, consider using Redis or database-backed memory.
    
    Attributes:
        messages (List[Dict]): The list of stored messages
    
    Example:
        >>> memory = InMemoryMemory()
        >>> memory.add_message({"role": "user", "content": "Hello!"})
        >>> memory.add_message({"role": "assistant", "content": "Hi there!"})
        >>> for msg in memory.get_messages():
        ...     print(f"{msg['role']}: {msg['content']}")
        user: Hello!
        assistant: Hi there!
    
    Thread Safety:
        This implementation is NOT thread-safe. For concurrent access,
        wrap operations in a lock or use a thread-safe implementation.
    """
    
    def __init__(self):
        """
        Initialize empty message storage.
        
        Creates a new empty list to store messages. Each instance has
        its own isolated message history.
        """
        self.messages: List[Dict[str, Any]] = []
        
    def add_message(self, message: Dict[str, Any]):
        """
        Add a message to the in-memory list.
        
        Messages are appended to the end of the list, maintaining
        chronological order.
        
        Args:
            message: Message dictionary to store
        """
        self.messages.append(message)
        
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Return the list of all stored messages.
        
        Returns:
            The internal message list. Note that this is a reference
            to the actual list, not a copy.
        
        Warning:
            Modifying the returned list will affect the memory state.
            If you need to modify messages, make a copy first.
        """
        return self.messages
        
    def clear(self):
        """
        Clear all messages by resetting to an empty list.
        
        This creates a new empty list rather than clearing the existing
        one, which ensures any external references are not affected.
        """
        self.messages = []
