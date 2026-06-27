"""
Configuration Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict

class ConfigurationPort(ABC):
    """Interface defining operations to retrieve and update system settings."""

    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve configuration setting by key. Supports dot-notation keys (e.g. 'llm.model')."""
        pass

    @abstractmethod
    def get_boolean(self, key: str, default: bool = False) -> bool:
        """Retrieve setting cast to a boolean value."""
        pass

    @abstractmethod
    def get_int(self, key: str, default: int = 0) -> int:
        """Retrieve setting cast to an integer value."""
        pass

    @abstractmethod
    def get_string(self, key: str, default: str = "") -> str:
        """Retrieve setting cast to a string."""
        pass

    @abstractmethod
    def set(self, key: str, value: Any) -> None:
        """Update or insert a configuration key value in memory."""
        pass

    @abstractmethod
    def load(self) -> None:
        """Load configuration from the primary persistence source (e.g. YAML, environment)."""
        pass

    @abstractmethod
    def validate(self) -> bool:
        """Validate current configuration state against a predefined schema.
        
        Raises:
            ConfigurationError: If the configuration fails schema check.
        """
        pass

    @abstractmethod
    def get_all(self) -> Dict[str, Any]:
        """Returns a copy of the entire configuration dictionary."""
        pass
