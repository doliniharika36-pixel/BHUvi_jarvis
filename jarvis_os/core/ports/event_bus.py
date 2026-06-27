"""
Event Bus Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Callable, Type, TypeVar
from jarvis_os.core.domain.events import DomainEvent

T = TypeVar('T', bound=DomainEvent)

class EventBusPort(ABC):
    """Interface defining the publish-subscribe messaging backbone."""

    @abstractmethod
    def publish(self, event: DomainEvent) -> None:
        """Publish a domain event to all registered subscribers."""
        pass

    @abstractmethod
    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Register an event handler callback for a specific domain event class type."""
        pass

    @abstractmethod
    def unsubscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Remove a registered event handler callback from a domain event class type."""
        pass
