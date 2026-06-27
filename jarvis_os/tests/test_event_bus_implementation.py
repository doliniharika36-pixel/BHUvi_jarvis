"""
Unit tests for SyncEventBus implementation of EventBusPort.
"""
import threading
import unittest
from dataclasses import dataclass, field
from datetime import datetime
from typing import List
import uuid

from jarvis_os.core.domain.events import DomainEvent, SystemBootstrappedEvent, SystemShutdownEvent
from jarvis_os.core.domain.exceptions import EventBusException
from jarvis_os.infrastructure.event_bus.sync_event_bus import SyncEventBus


# ---------------------------------------------------------------------------
# Helpers — lightweight custom events for isolation
# ---------------------------------------------------------------------------

@dataclass
class PingEvent(DomainEvent):
    payload: str = ""

@dataclass
class PongEvent(DomainEvent):
    payload: str = ""


# ---------------------------------------------------------------------------
# Test suite
# ---------------------------------------------------------------------------

class TestSyncEventBus(unittest.TestCase):
    """Comprehensive tests for SyncEventBus."""

    def setUp(self) -> None:
        self.bus = SyncEventBus()

    def tearDown(self) -> None:
        self.bus.clear()

    # ------------------------------------------------------------------ #
    # Basic subscribe / unsubscribe                                        #
    # ------------------------------------------------------------------ #

    def test_subscribe_registers_handler(self):
        """Subscriber count increases after subscribe."""
        handler = lambda e: None
        self.bus.subscribe(PingEvent, handler)
        self.assertEqual(self.bus.subscriber_count(PingEvent), 1)

    def test_unsubscribe_removes_handler(self):
        """Subscriber count decreases after unsubscribe."""
        handler = lambda e: None
        self.bus.subscribe(PingEvent, handler)
        self.bus.unsubscribe(PingEvent, handler)
        self.assertEqual(self.bus.subscriber_count(PingEvent), 0)

    def test_unsubscribe_unregistered_is_noop(self):
        """Unsubscribing a handler that was never registered raises no error."""
        handler = lambda e: None
        self.bus.unsubscribe(PingEvent, handler)  # must not raise

    def test_duplicate_subscribe_ignored(self):
        """Registering the same handler object twice registers it only once."""
        handler = lambda e: None
        self.bus.subscribe(PingEvent, handler)
        self.bus.subscribe(PingEvent, handler)
        self.assertEqual(self.bus.subscriber_count(PingEvent), 1)

    # ------------------------------------------------------------------ #
    # Event delivery                                                        #
    # ------------------------------------------------------------------ #

    def test_event_delivered_to_subscriber(self):
        """Published event is received by the subscribed handler."""
        received: List[PingEvent] = []
        self.bus.subscribe(PingEvent, received.append)

        event = PingEvent(payload="hello")
        self.bus.publish(event)

        self.assertEqual(len(received), 1)
        self.assertIs(received[0], event)

    def test_event_not_delivered_after_unsubscribe(self):
        """Handler does not receive events after it unsubscribes."""
        received: List[PingEvent] = []
        self.bus.subscribe(PingEvent, received.append)
        self.bus.unsubscribe(PingEvent, received.append)

        self.bus.publish(PingEvent(payload="should not arrive"))
        self.assertEqual(len(received), 0)

    def test_event_type_isolation(self):
        """Handlers for PingEvent are not called when PongEvent is published."""
        ping_received: List[PingEvent] = []
        pong_received: List[PongEvent] = []

        self.bus.subscribe(PingEvent, ping_received.append)
        self.bus.subscribe(PongEvent, pong_received.append)

        self.bus.publish(PongEvent(payload="pong"))

        self.assertEqual(len(ping_received), 0)
        self.assertEqual(len(pong_received), 1)

    def test_publish_with_no_subscribers_is_noop(self):
        """Publishing to a type with no subscribers completes without error."""
        self.bus.publish(PingEvent(payload="lonely"))  # must not raise

    # ------------------------------------------------------------------ #
    # Multiple subscribers                                                  #
    # ------------------------------------------------------------------ #

    def test_multiple_subscribers_all_receive_event(self):
        """All registered handlers receive the same published event."""
        buckets: List[List[PingEvent]] = [[], [], []]
        for bucket in buckets:
            self.bus.subscribe(PingEvent, bucket.append)

        event = PingEvent(payload="broadcast")
        self.bus.publish(event)

        for bucket in buckets:
            self.assertEqual(len(bucket), 1)
            self.assertIs(bucket[0], event)

    def test_dispatch_order_matches_registration_order(self):
        """Handlers are called in the exact order they were registered."""
        call_order: List[int] = []

        for i in range(5):
            # Default argument captures loop variable correctly
            def make_handler(n):
                return lambda e: call_order.append(n)
            self.bus.subscribe(PingEvent, make_handler(i))

        self.bus.publish(PingEvent())
        self.assertEqual(call_order, [0, 1, 2, 3, 4])

    # ------------------------------------------------------------------ #
    # Exception isolation                                                   #
    # ------------------------------------------------------------------ #

    def test_failing_handler_does_not_stop_remaining_handlers(self):
        """If handler N raises, handlers N+1 … still execute."""
        results: List[str] = []

        def good_first(e):
            results.append("first")

        def bad_middle(e):
            results.append("bad")
            raise RuntimeError("Simulated handler failure")

        def good_last(e):
            results.append("last")

        self.bus.subscribe(PingEvent, good_first)
        self.bus.subscribe(PingEvent, bad_middle)
        self.bus.subscribe(PingEvent, good_last)

        # publish must not raise even though bad_middle does
        self.bus.publish(PingEvent())

        self.assertEqual(results, ["first", "bad", "last"])

    def test_all_failing_handlers_still_completes(self):
        """If every handler raises, publish still returns normally."""
        for _ in range(3):
            self.bus.subscribe(PingEvent, lambda e: (_ for _ in ()).throw(ValueError("fail")))

        self.bus.publish(PingEvent())  # must not propagate

    # ------------------------------------------------------------------ #
    # Re-entrant publishing                                                 #
    # ------------------------------------------------------------------ #

    def test_handler_may_publish_new_event(self):
        """A handler may safely publish a different event type without deadlocking."""
        pong_received: List[PongEvent] = []
        self.bus.subscribe(PongEvent, pong_received.append)

        def ping_handler(e: PingEvent):
            self.bus.publish(PongEvent(payload="from-ping"))

        self.bus.subscribe(PingEvent, ping_handler)
        self.bus.publish(PingEvent())

        self.assertEqual(len(pong_received), 1)
        self.assertEqual(pong_received[0].payload, "from-ping")

    def test_handler_may_subscribe_during_dispatch(self):
        """A handler may call subscribe() mid-dispatch without crashing."""
        late_received: List[PingEvent] = []

        def early_handler(e: PingEvent):
            # Subscribes a new handler during dispatch — should not affect THIS round
            self.bus.subscribe(PingEvent, late_received.append)

        self.bus.subscribe(PingEvent, early_handler)
        self.bus.publish(PingEvent(payload="round-1"))

        # late_received is empty for round-1 (snapshot semantics)
        self.assertEqual(len(late_received), 0)

        # But the new handler IS active for round-2
        self.bus.publish(PingEvent(payload="round-2"))
        self.assertEqual(len(late_received), 1)

    # ------------------------------------------------------------------ #
    # Validation / error handling                                           #
    # ------------------------------------------------------------------ #

    def test_subscribe_non_callable_raises(self):
        """Registering a non-callable handler raises EventBusException."""
        with self.assertRaises(EventBusException):
            self.bus.subscribe(PingEvent, "not_a_function")  # type: ignore[arg-type]

    def test_publish_non_domain_event_raises(self):
        """Publishing an object that is not a DomainEvent raises EventBusException."""
        with self.assertRaises(EventBusException):
            self.bus.publish("raw string")  # type: ignore[arg-type]

    # ------------------------------------------------------------------ #
    # Thread safety                                                         #
    # ------------------------------------------------------------------ #

    def test_concurrent_publish_is_thread_safe(self):
        """Many threads publishing simultaneously produce no data races."""
        counter_lock = threading.Lock()
        counter = {"value": 0}

        def increment(e: PingEvent):
            with counter_lock:
                counter["value"] += 1

        self.bus.subscribe(PingEvent, increment)

        threads = [
            threading.Thread(target=self.bus.publish, args=(PingEvent(),))
            for _ in range(50)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(counter["value"], 50)

    def test_concurrent_subscribe_unsubscribe_is_thread_safe(self):
        """Concurrent subscribe/unsubscribe operations do not corrupt internal state."""
        handlers = [lambda e: None for _ in range(20)]
        errors: List[Exception] = []

        def subscribe_all():
            try:
                for h in handlers:
                    self.bus.subscribe(PingEvent, h)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        def unsubscribe_all():
            try:
                for h in handlers:
                    self.bus.unsubscribe(PingEvent, h)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=subscribe_all) for _ in range(5)] + \
                  [threading.Thread(target=unsubscribe_all) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])

    # ------------------------------------------------------------------ #
    # clear()                                                               #
    # ------------------------------------------------------------------ #

    def test_clear_removes_all_subscribers(self):
        """clear() causes no handlers to run on subsequent publish."""
        received: List[PingEvent] = []
        self.bus.subscribe(PingEvent, received.append)
        self.bus.clear()

        self.bus.publish(PingEvent())
        self.assertEqual(len(received), 0)
        self.assertEqual(self.bus.subscriber_count(PingEvent), 0)


if __name__ == "__main__":
    unittest.main()
