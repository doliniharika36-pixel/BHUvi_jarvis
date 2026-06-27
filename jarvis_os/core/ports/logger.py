"""
Logger Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Any, Optional

class LoggerPort(ABC):
    """Interface defining structured logging functionality for all subsystems."""

    @abstractmethod
    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug-level message with optional key-value structured details."""
        pass

    @abstractmethod
    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info-level message with optional key-value structured details."""
        pass

    @abstractmethod
    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning-level message with optional key-value structured details."""
        pass

    @abstractmethod
    def error(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log an error-level message with an optional exception object and structured details."""
        pass

    @abstractmethod
    def critical(self, message: str, error: Optional[Exception] = None, **kwargs: Any) -> None:
        """Log a critical failure event with an optional exception and metadata."""
        pass

    @abstractmethod
    def set_level(self, level: str) -> None:
        """Set the active logging threshold (e.g., 'DEBUG', 'INFO', 'WARNING', 'ERROR')."""
        pass
