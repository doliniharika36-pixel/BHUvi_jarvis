"""
Repository Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Generic, List, Optional, TypeVar
from jarvis_os.core.domain.entities import ConfigEntry, LogRecord

T = TypeVar('T')

class RepositoryPort(Generic[T], ABC):
    """Generic interface for data-access and persistence operations of domain entities."""

    @abstractmethod
    def save(self, entity: T) -> None:
        """Persist a new entity or overwrite an existing entity in the store.
        
        Raises:
            RepositoryException: If database execution fails.
        """
        pass

    @abstractmethod
    def get_by_id(self, entity_id: str) -> Optional[T]:
        """Fetch a single entity from the store by its unique string identifier.
        
        Raises:
            RepositoryException: If database execution fails.
        """
        pass

    @abstractmethod
    def delete(self, entity_id: str) -> None:
        """Remove an entity from the store by its identifier.
        
        Raises:
            RepositoryException: If database execution fails.
        """
        pass

    @abstractmethod
    def list_all(self) -> List[T]:
        """Retrieve a list of all matching records currently in the repository.
        
        Raises:
            RepositoryException: If database execution fails.
        """
        pass


class ConfigRepositoryPort(RepositoryPort[ConfigEntry], ABC):
    """Specific repository interface for system settings configuration entities."""
    
    @abstractmethod
    def get_by_key(self, key: str) -> Optional[ConfigEntry]:
        """Query a configuration item specifically by its configuration key string."""
        pass


class LogRepositoryPort(RepositoryPort[LogRecord], ABC):
    """Specific repository interface for persisting system log entries."""
    
    @abstractmethod
    def get_logs_by_level(self, level: str) -> List[LogRecord]:
        """Query a filtered list of log records by severity level string."""
        pass

    @abstractmethod
    def purge_old_logs(self, before_timestamp: str) -> int:
        """Delete historical logs written before a given ISO datetime string, returning count."""
        pass
