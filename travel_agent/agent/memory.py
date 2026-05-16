from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from ..config import Config


class AgentMemory(ABC):
    """Abstract base class for agent memory."""

    @abstractmethod
    def add_message(self, message: Dict[str, Any]) -> None: ...

    @abstractmethod
    def get_messages(self) -> List[Dict[str, Any]]: ...

    @abstractmethod
    def clear(self) -> None: ...


class InMemoryMemory(AgentMemory):
    """Sliding-window conversation memory.

    Keeps only the most recent `max_messages` entries to bound memory growth
    in long-running sessions. Default comes from Config.MAX_MESSAGES.
    """

    def __init__(self, max_messages: Optional[int] = None):
        self._max = max_messages if max_messages is not None else Config.MAX_MESSAGES
        if self._max < 1:
            raise ValueError("max_messages must be >= 1")
        self.messages: List[Dict[str, Any]] = []

    def add_message(self, message: Dict[str, Any]) -> None:
        if "role" not in message:
            raise ValueError("message must include 'role'")
        self.messages.append(message)
        # Trim oldest non-system messages once over the cap.
        if len(self.messages) > self._max:
            overflow = len(self.messages) - self._max
            del self.messages[:overflow]

    def get_messages(self) -> List[Dict[str, Any]]:
        return list(self.messages)

    def clear(self) -> None:
        self.messages.clear()
