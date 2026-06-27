"""
LLM Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from jarvis_os.core.domain.entities import LLMMessage, LLMResponse

class LLMPort(ABC):
    """Interface defining basic natural language and semantic embedding capabilities."""

    @abstractmethod
    def generate(self, prompt: str, options: Optional[Dict[str, Any]] = None) -> str:
        """Execute a text completion generation query.
        
        Raises:
            LLMException: If communication or processing fails.
        """
        pass

    @abstractmethod
    def chat(self, messages: List[LLMMessage], options: Optional[Dict[str, Any]] = None) -> LLMResponse:
        """Execute a chat-based generation conversation using domain-modeled messages.
        
        Raises:
            LLMException: If communication or processing fails.
        """
        pass

    @abstractmethod
    def embed(self, text: str) -> List[float]:
        """Convert a block of text into a vector embedding array of float numbers.
        
        Raises:
            LLMException: If embedding generation fails.
        """
        pass
