"""
Synchronous, thread-safe Event Bus implementation for Jarvis OS.

Design decisions:
- Uses threading.RLock so handlers may publish further events (re-entrant).
- Dispatches to a snapshot copy of the subscriber list so subscribe/unsubscribe
  during dispatch is safe and does not affect the current round.
- Continues dispatching to remaining handlers if one raises an exception;
  errors are emitted to stderr (a logger is deliberately NOT injected here to
  avoid a circular dependency — LoggerPort depends on nothing, EventBus depends
  on nothing, both are leaf nodes).
- Pure stdlib: threading, collections, traceback.
"""
import threading
import traceback
from collections import defaultdict
from typing import Callable, Dict, List, Type, TypeVar

from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.domain.events import DomainEvent
from jarvis_os.core.domain.exceptions import EventBusException

T = TypeVar("T", bound=DomainEvent)


class SyncEventBus(EventBusPort):
    """Synchronous, thread-safe publish-subscribe event bus.

    All handlers for a given event type are invoked in the order they were
    registered, on the calling thread.  Handler exceptions are caught,
    reported, and do NOT stop remaining handlers from running.
    """

    def __init__(self) -> None:
        # Maps event type → ordered list of callables
        self._subscribers: Dict[Type[DomainEvent], List[Callable[[DomainEvent], None]]] = defaultdict(list)
        # RLock: allows a handler to publish a new event without deadlocking
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # EventBusPort interface                                               #
    # ------------------------------------------------------------------ #

    def subscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Register *handler* to be called whenever *event_type* is published.

        Raises:
            EventBusException: If handler is not callable.
        """
        if not callable(handler):
            raise EventBusException(f"Handler must be callable, got: {type(handler)}")

        with self._lock:
            # Prevent duplicate registration of the exact same handler object
            if handler not in self._subscribers[event_type]:  # type: ignore[arg-type]
                self._subscribers[event_type].append(handler)  # type: ignore[arg-type]

    def unsubscribe(self, event_type: Type[T], handler: Callable[[T], None]) -> None:
        """Remove *handler* from the subscriber list for *event_type*.

        Silently ignores the call if the handler was never registered,
        matching standard observer-pattern conventions.
        """
        with self._lock:
            try:
                self._subscribers[event_type].remove(handler)  # type: ignore[arg-type]
            except ValueError:
                pass  # Not registered — no-op

    def publish(self, event: DomainEvent) -> None:
        """Dispatch *event* to all handlers registered for its exact type.

        Handler execution order matches registration order.
        Each handler is called synchronously on the calling thread.
        A failing handler is isolated: its traceback is printed and dispatch
        continues with the remaining handlers.

        Raises:
            EventBusException: If *event* is not a DomainEvent instance.
        """
        if not isinstance(event, DomainEvent):
            raise EventBusException(
                f"Published object must be a DomainEvent, got: {type(event)}"
            )

        event_type = type(event)

        # Take a snapshot under the lock so subscribe/unsubscribe during
        # dispatch does not mutate the list we are iterating
        with self._lock:
            handlers = list(self._subscribers.get(event_type, []))

        # Dispatch OUTSIDE the lock so handlers may call subscribe/unsubscribe/publish
        for handler in handlers:
            try:
                handler(event)  # type: ignore[arg-type]
            except Exception:  # noqa: BLE001
                # Isolation: log the traceback but keep dispatching
                traceback.print_exc()

    # ------------------------------------------------------------------ #
    # Introspection helpers (not part of the port; useful for testing)    #
    # ------------------------------------------------------------------ #

    def subscriber_count(self, event_type: Type[DomainEvent]) -> int:
        """Return the number of handlers currently registered for *event_type*."""
        with self._lock:
            return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """Remove all subscribers (useful for test teardown)."""
        with self._lock:
            self._subscribers.clear()
