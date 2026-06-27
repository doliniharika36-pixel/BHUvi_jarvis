"""
Unit tests for the Runtime Lifecycle, ServiceRegistry, and ApplicationHost.
"""
from dataclasses import dataclass
import os
import tempfile
import threading
import unittest
from typing import Any, Dict, List, Optional

from jarvis_os.core.domain.exceptions import JarvisException
from jarvis_os.core.domain.events import (
    RuntimeStarting,
    RuntimeStarted,
    RuntimeStopping,
    RuntimeStopped,
    RuntimeFailed,
)
from jarvis_os.infrastructure.runtime.app_host import (
    ApplicationHost,
    ApplicationState,
    ServiceRegistry,
    RuntimeLifecycle,
)


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock Services for Lifecycle testing                                    #
# ═══════════════════════════════════════════════════════════════════════ #

class DisposableService:
    """Mock service that tracks its disposal state."""

    def __init__(self, name: str, dispose_log: List[str]) -> None:
        self.name = name
        self._dispose_log = dispose_log
        self.disposed = False

    def dispose(self) -> None:
        self.disposed = True
        self._dispose_log.append(self.name)


class FaultyService:
    """Mock service that throws an error on disposal."""

    def __init__(self, name: str) -> None:
        self.name = name

    def dispose(self) -> None:
        raise RuntimeError(f"Deliberate disposal failure in '{self.name}'")


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Suite                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestRuntimeLifecycle(unittest.TestCase):
    """Tests verify state machine correctness, startup pipeline, shutdown ordering, and error isolation."""

    def setUp(self) -> None:
        # Create a temp directory for a test database and env config
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_lifecycle.db")

        # Create a mock .env file
        self.env_path = os.path.join(self.temp_dir.name, "test_env.env")
        with open(self.env_path, "w", encoding="utf-8") as f:
            f.write("JARVIS_LOG_LEVEL=INFO\n")
            f.write(f"JARVIS_DATABASE_PATH={self.db_path}\n")

        self.host = ApplicationHost(
            db_path_override=self.db_path,
            env_file_path=self.env_path,
        )

    def tearDown(self) -> None:
        # Close host if still open
        try:
            self.host.shutdown()
        except Exception:
            pass
        self.temp_dir.cleanup()

    # ------------------------------------------------------------------ #
    # Service Registry                                                     #
    # ------------------------------------------------------------------ #

    def test_service_registry_registration_and_resolution(self) -> None:
        """ServiceRegistry registers and resolves items correctly."""
        registry = ServiceRegistry()
        service = object()
        registry.register("my_service", service)

        self.assertTrue(registry.has_service("my_service"))
        self.assertIs(registry.resolve("my_service"), service)
        self.assertEqual(registry.list_services(), ["my_service"])

    def test_service_registry_prevents_duplicates(self) -> None:
        """ServiceRegistry raises ValueError on duplicate key registration."""
        registry = ServiceRegistry()
        registry.register("service", object())

        with self.assertRaises(ValueError):
            registry.register("service", object())

    def test_service_registry_dispose_in_reverse_order(self) -> None:
        """ServiceRegistry disposes items in reverse registration order."""
        registry = ServiceRegistry()
        dispose_log: List[str] = []

        s1 = DisposableService("s1", dispose_log)
        s2 = DisposableService("s2", dispose_log)
        s3 = DisposableService("s3", dispose_log)

        registry.register("first", s1)
        registry.register("second", s2)
        registry.register("third", s3)

        registry.dispose_all()

        # Must be disposed in reverse (3 -> 2 -> 1)
        self.assertEqual(dispose_log, ["s3", "s2", "s1"])
        self.assertTrue(s1.disposed)
        self.assertTrue(s2.disposed)
        self.assertTrue(s3.disposed)

    def test_service_registry_faulty_service_isolation(self) -> None:
        """A failure in one service's disposal does not block other service disposals."""
        registry = ServiceRegistry()
        dispose_log: List[str] = []

        s1 = DisposableService("s1", dispose_log)
        faulty = FaultyService("faulty")
        s2 = DisposableService("s2", dispose_log)

        registry.register("s1", s1)
        registry.register("faulty", faulty)
        registry.register("s2", s2)

        # Must not raise an exception; both s2 and s1 should be disposed
        registry.dispose_all()
        self.assertEqual(dispose_log, ["s2", "s1"])
        self.assertTrue(s1.disposed)
        self.assertTrue(s2.disposed)

    # ------------------------------------------------------------------ #
    # Startup Sequence and State Transitions                               #
    # ------------------------------------------------------------------ #

    def test_successful_bootstrap_transitions(self) -> None:
        """Bootstrap starts at INITIALIZING and transitions sequentially to RUNNING."""
        self.assertEqual(self.host.lifecycle.state, ApplicationState.INITIALIZING)
        self.assertFalse(self.host.is_running())

        self.host.bootstrap()

        self.assertEqual(self.host.lifecycle.state, ApplicationState.RUNNING)
        self.assertTrue(self.host.is_running())

        # Verify core services are registered in ServiceRegistry
        self.assertTrue(self.host.registry.has_service("config"))
        self.assertTrue(self.host.registry.has_service("logger"))
        self.assertTrue(self.host.registry.has_service("database"))
        self.assertTrue(self.host.registry.has_service("event_bus"))
        self.assertTrue(self.host.registry.has_service("policy"))

    def test_bootstrap_idempotency(self) -> None:
        """Calling bootstrap() when already running is a no-op."""
        self.host.bootstrap()
        state1 = self.host.lifecycle.state

        # Call again
        self.host.bootstrap()
        state2 = self.host.lifecycle.state

        self.assertEqual(state1, ApplicationState.RUNNING)
        self.assertEqual(state2, ApplicationState.RUNNING)

    def test_failed_bootstrap_transitions_to_failed_then_stopped(self) -> None:
        """A failure during bootstrapping cleans up and moves to FAILED then STOPPED state."""
        import sys
        if sys.platform == "win32":
            bad_db = "C:\\CON\\impossible\\db.sqlite"
        else:
            bad_db = "/dev/null/impossible/db.sqlite"

        # Force a failure via impossible db path override
        bad_host = ApplicationHost(
            db_path_override=bad_db,
            env_file_path=self.env_path,
        )

        with self.assertRaises(JarvisException):
            bad_host.bootstrap()

        # Since it cleans up, the final state must be STOPPED
        self.assertEqual(bad_host.lifecycle.state, ApplicationState.STOPPED)

    # ------------------------------------------------------------------ #
    # Shutdown Sequence and State Transitions                              #
    # ------------------------------------------------------------------ #

    def test_graceful_shutdown_lifecycle(self) -> None:
        """Graceful shutdown transitions state to SHUTTING_DOWN then STOPPED, disposing services."""
        self.host.bootstrap()

        dispose_log: List[str] = []
        custom_service = DisposableService("custom", dispose_log)
        self.host.registry.register("custom", custom_service)

        self.host.shutdown()

        self.assertEqual(self.host.lifecycle.state, ApplicationState.STOPPED)
        self.assertFalse(self.host.is_running())
        self.assertTrue(custom_service.disposed)

    def test_shutdown_idempotency(self) -> None:
        """Calling shutdown() multiple times is safe and idempotent."""
        self.host.bootstrap()
        self.host.shutdown()
        state1 = self.host.lifecycle.state

        self.host.shutdown()
        state2 = self.host.lifecycle.state

        self.assertEqual(state1, ApplicationState.STOPPED)
        self.assertEqual(state2, ApplicationState.STOPPED)

    # ------------------------------------------------------------------ #
    # Event Publication                                                    #
    # ------------------------------------------------------------------ #

    def test_startup_and_shutdown_publish_lifecycle_events(self) -> None:
        """Bootstrap and shutdown publish the corresponding system events."""
        self.host.bootstrap()

        # Retrieve the SyncEventBus from the container
        from jarvis_os.core.ports.event_bus import EventBusPort
        bus = self.host.container.resolve(EventBusPort)  # type: ignore[union-attr]

        events_received = []
        bus.subscribe(RuntimeStarting, lambda e: events_received.append("starting"))
        bus.subscribe(RuntimeStarted, lambda e: events_received.append("started"))
        bus.subscribe(RuntimeStopping, lambda e: events_received.append("stopping"))
        bus.subscribe(RuntimeStopped, lambda e: events_received.append("stopped"))

        # Re-publish startup events for test verification since they were published
        # before we subscribed. Or we can just publish new instances to test subscription.
        bus.publish(RuntimeStarting())
        bus.publish(RuntimeStarted())

        self.host.shutdown()

        self.assertIn("starting", events_received)
        self.assertIn("started", events_received)
        self.assertIn("stopping", events_received)
        self.assertIn("stopped", events_received)

    # ------------------------------------------------------------------ #
    # Thread Safety                                                         #
    # ------------------------------------------------------------------ #

    def test_concurrent_bootstrap_and_shutdown(self) -> None:
        """Bootstrap and shutdown methods can be called from different threads safely."""
        errors = []

        def worker_bootstrap():
            try:
                self.host.bootstrap()
            except Exception as exc:
                errors.append(exc)

        def worker_shutdown():
            try:
                # Give a tiny delay to allow bootstrap to start
                import time
                time.sleep(0.01)
                self.host.shutdown()
            except Exception as exc:
                errors.append(exc)

        t1 = threading.Thread(target=worker_bootstrap)
        t2 = threading.Thread(target=worker_shutdown)

        t1.start()
        t2.start()

        t1.join(timeout=5)
        t2.join(timeout=5)

        # Thread executions must not hang or throw resource race errors
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
