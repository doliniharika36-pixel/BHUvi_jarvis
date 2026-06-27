"""
Contract Test for EventBusPort.
"""
import unittest
from typing import Any, Callable, Dict, List, Type, TypeVar
from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.domain.events import DomainEvent, SystemBootstrappedEvent

T = TypeVar('T', bound=DomainEvent)

class TestEventBusPortContract(unittest.TestCase):
    """Verifies that the EventBusPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the EventBusPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            EventBusPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteBus(EventBusPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteBus()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated and operated."""
        class MockEventBus(EventBusPort):
            def __init__(self):
                self._listeners: Dict[Type[DomainEvent], List[Callable[[Any], None]]] = {}

            def publish(self, event: DomainEvent) -> None:
                event_type = type(event)
                if event_type in self._listeners:
                    for callback in self._listeners[event_type]:
                        callback(event)

            def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
                if event_type not in self._listeners:
                    self._listeners[event_type] = []
                self._listeners[event_type].append(handler)  # type: ignore

            def unsubscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
                if event_type in self._listeners:
                    self._listeners[event_type].remove(handler)  # type: ignore

        bus = MockEventBus()
        self.assertIsInstance(bus, EventBusPort)
        
        events_received = []
        def handler(event: SystemBootstrappedEvent):
            events_received.append(event)

        # Test subscription
        bus.subscribe(SystemBootstrappedEvent, handler)
        
        # Test publication
        boot_event = SystemBootstrappedEvent(startup_time_ms=150.0)
        bus.publish(boot_event)
        
        self.assertEqual(len(events_received), 1)
        self.assertEqual(events_received[0].startup_time_ms, 150.0)
        
        # Test unsubscription
        bus.unsubscribe(SystemBootstrappedEvent, handler)
        bus.publish(boot_event)
        
        self.assertEqual(len(events_received), 1)  # count remains 1 since unsubscribed

if __name__ == "__main__":
    unittest.main()
