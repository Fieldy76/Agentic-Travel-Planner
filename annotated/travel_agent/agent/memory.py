# Import ABC (Abstract Base Class) to define interfaces
from abc import ABC, abstractmethod
# Import type hints for better code documentation
from typing import List, Dict, Any

class AgentMemory(ABC):
    """
    Abstract base class for agent memory systems.
    
    This interface allows us to swap memory implementations without changing
    the orchestrator code. For example:
    - InMemoryMemory for development/testing
    - RedisMemory for distributed systems
    - DatabaseMemory for persistent storage
    """
    
    @abstractmethod
    def add_message(self, message: Dict[str, Any]):
        """
        Add a message to the conversation history.
        
        Args:
            message: A message dict with 'role' and 'content' keys
                    Role can be: 'user', 'assistant', 'tool', or 'system'
        """
        pass
        
    @abstractmethod
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Retrieve all messages in the conversation history.
        
        Returns:
            List of message dictionaries in chronological order
        """
        pass
        
    @abstractmethod
    def clear(self):
        """
        Clear all messages from memory.
        
        Useful for starting a new conversation or resetting state.
        """
        pass

class InMemoryMemory(AgentMemory):
    """
    Simple in-memory storage for agent messages.
    
    This is suitable for:
    - Development and testing
    - Single-process deployments
    - Short-lived conversations
    
    Limitations:
    - Data is lost when the process restarts
    - Not suitable for multi-process/distributed systems
    - No persistence across sessions
    """
    
    def __init__(self):
        """Initialize with an empty message list."""
        # Store messages as a simple Python list
        # Each message is a dictionary with role, content, and optional metadata
        self.messages: List[Dict[str, Any]] = []
        
    def add_message(self, message: Dict[str, Any]):
        """
        Add a message to the in-memory list.
        
        Args:
            message: Dictionary representing a conversation message
        """
        # Simply append to the list - chronological order is maintained
        self.messages.append(message)
        
    def get_messages(self) -> List[Dict[str, Any]]:
        """
        Get all messages from memory.
        
        Returns:
            The full message list (by reference, not a copy)
        """
        return self.messages
        
    def clear(self):
        """
        Clear all messages from memory.
        
        Creates a new empty list, allowing garbage collection of old messages.
        """
        self.messages = []
