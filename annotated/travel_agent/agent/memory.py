from abc import ABC, abstractmethod
from typing import List, Dict, Any

class AgentMemory(ABC):
    """Abstract base class for agent memory."""
    
    @abstractmethod
    def add_message(self, message: Dict[str, Any]):
        """Add a message to memory."""
        pass
        
    @abstractmethod
    def get_messages(self) -> List[Dict[str, Any]]:
        """Retrieve all messages."""
        pass
        
    @abstractmethod
    def clear(self):
        """Clear memory."""
        pass

class InMemoryMemory(AgentMemory):
    """Simple in-memory storage for agent messages."""
    
    def __init__(self):
        self.messages: List[Dict[str, Any]] = []
        
    def add_message(self, message: Dict[str, Any]):
        self.messages.append(message)
        
    def get_messages(self) -> List[Dict[str, Any]]:
        return self.messages
        
    def clear(self):
        self.messages = []
