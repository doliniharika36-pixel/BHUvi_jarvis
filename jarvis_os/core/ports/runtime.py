"""
Runtime Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod

class RuntimePort(ABC):
    """Interface defining system lifecycle controls."""

    @abstractmethod
    def bootstrap(self) -> None:
        """Initialize all subsystems, run schema migrations, and trigger setup policies.
        
        Raises:
            JarvisException: If bootstrap checks or initialization fails.
        """
        pass

    @abstractmethod
    def shutdown(self) -> None:
        """Stop all background worker threads, close active DB connections, and release ports."""
        pass

    @abstractmethod
    def is_running(self) -> bool:
        """Return whether the core runtime is currently active and processing events."""
        pass
