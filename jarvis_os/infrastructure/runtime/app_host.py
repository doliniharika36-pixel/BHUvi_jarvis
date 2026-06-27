"""
Deterministic Runtime Lifecycle Manager and Application Host for Jarvis OS.

Exposes the ApplicationHost which coordinates configuration, DI container setup,
logging initialization, SQLite connections, Repository framework, Event Bus,
Policy Engine, and custom service lifecycles.
"""
from enum import Enum
import time
import threading
from typing import Any, Dict, List, Optional

from jarvis_os.core.ports.runtime import RuntimePort
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.ports.logger import LoggerPort
from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.domain.exceptions import JarvisException
from jarvis_os.core.domain.events import (
    RuntimeStarting,
    RuntimeStarted,
    RuntimeStopping,
    RuntimeStopped,
    RuntimeFailed,
)

# Concrete infrastructure imports for bootstrapping
from jarvis_os.core.di import DIContainer
from jarvis_os.infrastructure.config.settings import EnvSettings
from jarvis_os.infrastructure.logger.structured_logger import StructuredLogger
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager
from jarvis_os.infrastructure.event_bus.sync_event_bus import SyncEventBus
from jarvis_os.infrastructure.policy.policy_engine import PolicyEngine


# ═══════════════════════════════════════════════════════════════════════ #
#  States and Lifecycle                                                    #
# ═══════════════════════════════════════════════════════════════════════ #

class ApplicationState(Enum):
    INITIALIZING = "INITIALIZING"
    BOOTSTRAPPING = "BOOTSTRAPPING"
    CONFIG_LOADED = "CONFIG_LOADED"
    DI_READY = "DI_READY"
    INFRASTRUCTURE_READY = "INFRASTRUCTURE_READY"
    RUNNING = "RUNNING"
    SHUTTING_DOWN = "SHUTTING_DOWN"
    STOPPED = "STOPPED"
    FAILED = "FAILED"


class RuntimeLifecycle:
    """Manages thread-safe state transitions of the application host."""

    def __init__(self) -> None:
        self._state = ApplicationState.INITIALIZING
        self._lock = threading.RLock()

    @property
    def state(self) -> ApplicationState:
        with self._lock:
            return self._state

    def transition_to(self, target_state: ApplicationState) -> None:
        """Move the runtime into the target state thread-safely."""
        with self._lock:
            self._state = target_state


# ═══════════════════════════════════════════════════════════════════════ #
#  Service Registry                                                       #
# ═══════════════════════════════════════════════════════════════════════ #

class ServiceRegistry:
    """Tracks and disposes services cleanly without knowing implementation details."""

    def __init__(self) -> None:
        self._services: Dict[str, Any] = {}
        self._lock = threading.RLock()

    def register(self, name: str, service: Any) -> None:
        """Register a service. Prevents duplicate registrations."""
        with self._lock:
            if name in self._services:
                raise ValueError(f"Duplicate service registration detected: '{name}'")
            self._services[name] = service

    def resolve(self, name: str) -> Any:
        """Retrieve a registered service."""
        with self._lock:
            if name not in self._services:
                raise KeyError(f"Service not found: '{name}'")
            return self._services[name]

    def has_service(self, name: str) -> bool:
        """Check if a service exists in the registry."""
        with self._lock:
            return name in self._services

    def list_services(self) -> List[str]:
        """Return names of all registered services."""
        with self._lock:
            return list(self._services.keys())

    def dispose_all(self) -> None:
        """Dispose/close all registered services in reverse registration order."""
        with self._lock:
            for name in reversed(list(self._services.keys())):
                service = self._services[name]
                try:
                    # Clean shutdown via duck-typing for loose coupling
                    if hasattr(service, "dispose") and callable(service.dispose):
                        service.dispose()
                    elif hasattr(service, "close") and callable(service.close):
                        service.close()
                except Exception as exc:
                    # Report but do not halt subsequent service disposal
                    print(f"Error while disposing service '{name}': {exc}")
            self._services.clear()


# ═══════════════════════════════════════════════════════════════════════ #
#  Bootstrap Manager                                                      #
# ═══════════════════════════════════════════════════════════════════════ #

class BootstrapManager:
    """Coordinates the deterministic initialization of all system components."""

    def __init__(
        self,
        lifecycle: RuntimeLifecycle,
        registry: ServiceRegistry,
        db_path_override: Optional[str] = None,
        env_file_path: Optional[str] = None,
    ) -> None:
        self._lifecycle = lifecycle
        self._registry = registry
        self._db_path_override = db_path_override
        self._env_file_path = env_file_path

    def run(self) -> DIContainer:
        """Execute the deterministic startup pipeline.

        Returns:
            The configured DI Container.
        """
        start_time = time.perf_counter()

        self._lifecycle.transition_to(ApplicationState.BOOTSTRAPPING)

        # 1. Load configuration
        config = EnvSettings(env_file_path=self._env_file_path)
        config.load()
        config.validate()
        self._lifecycle.transition_to(ApplicationState.CONFIG_LOADED)

        # Override DB path for testing if needed
        db_path = self._db_path_override or config.get("database.path", "jarvis.db")

        # 2. Initialize structured logging
        logger = StructuredLogger(config)

        # 3. Build Dependency Injection container
        container = DIContainer()
        container.register_instance(ConfigurationPort, config)
        container.register_instance(LoggerPort, logger)
        self._lifecycle.transition_to(ApplicationState.DI_READY)

        # 4. Initialize SQLite foundation
        db_manager = SQLiteConnectionManager(db_path)
        db_manager.open()
        container.register_instance(SQLiteConnectionManager, db_manager)

        # 5. Initialize Repository Framework (Registers base SQLite components)
        # Note: Generic repository is used dynamically by consumers, registered instances not needed

        # 6. Initialize Event Bus
        event_bus = SyncEventBus()
        container.register_instance(EventBusPort, event_bus)

        # 7. Initialize Policy Engine
        policy_engine = PolicyEngine()
        container.register_instance(PolicyPort, policy_engine)

        self._lifecycle.transition_to(ApplicationState.INFRASTRUCTURE_READY)

        # 8. Register services
        self._registry.register("config", config)
        self._registry.register("logger", logger)
        self._registry.register("database", db_manager)
        self._registry.register("event_bus", event_bus)
        self._registry.register("policy", policy_engine)

        # 9. Publish Startup event
        event_bus.publish(RuntimeStarting())
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        event_bus.publish(RuntimeStarted(startup_time_ms=elapsed_ms))

        # 10. Transition to RUNNING
        self._lifecycle.transition_to(ApplicationState.RUNNING)

        return container


# ═══════════════════════════════════════════════════════════════════════ #
#  Application Host                                                       #
# ═══════════════════════════════════════════════════════════════════════ #

class ApplicationHost(RuntimePort):
    """The central orchestrator managing runtime lifecycle and service coordination."""

    def __init__(
        self,
        db_path_override: Optional[str] = None,
        env_file_path: Optional[str] = None,
    ) -> None:
        self.lifecycle = RuntimeLifecycle()
        self.registry = ServiceRegistry()
        self.container: Optional[DIContainer] = None
        self._db_path_override = db_path_override
        self._env_file_path = env_file_path
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # RuntimePort Implementation                                           #
    # ------------------------------------------------------------------ #

    def bootstrap(self) -> None:
        """Start the application pipeline and transition states."""
        with self._lock:
            if self.lifecycle.state == ApplicationState.RUNNING:
                return  # Idempotent: already running

            bootstrap_manager = BootstrapManager(
                lifecycle=self.lifecycle,
                registry=self.registry,
                db_path_override=self._db_path_override,
                env_file_path=self._env_file_path,
            )

            try:
                self.container = bootstrap_manager.run()
            except Exception as exc:
                self._handle_bootstrap_failure(exc)
                raise JarvisException(f"Application host bootstrap failed: {exc}") from exc

    def shutdown(self) -> None:
        """Shutdown in reverse dependency order (idempotently)."""
        with self._lock:
            state = self.lifecycle.state
            if state in (ApplicationState.STOPPED, ApplicationState.INITIALIZING):
                return  # Idempotent: already stopped or not started yet

            self.lifecycle.transition_to(ApplicationState.SHUTTING_DOWN)

            # Retrieve event bus to publish shutdown progress
            event_bus: Optional[EventBusPort] = None
            if self.container:
                try:
                    event_bus = self.container.resolve(EventBusPort)
                except Exception:
                    pass

            # 2. Publish Shutdown event (RuntimeStopping)
            if event_bus:
                try:
                    event_bus.publish(RuntimeStopping(reason="Graceful Shutdown Request"))
                except Exception:
                    pass

            # 3. Stop accepting new work & 4. Flush pending events
            # (SyncEventBus requires no active work queue flushes, but we clean up)
            if event_bus:
                try:
                    event_bus.publish(RuntimeStopped())
                except Exception:
                    pass

            # 5. Close repositories & 6. Close SQLite & 7. Dispose services
            # Exited via ServiceRegistry.dispose_all() in reverse order
            self.registry.dispose_all()

            # 8. Flush logger
            # StructuredLogger handlers are cleaned up during registry disposal/garbage collection

            # 9. Transition to STOPPED
            self.lifecycle.transition_to(ApplicationState.STOPPED)

    def is_running(self) -> bool:
        """Return true if state is RUNNING."""
        return self.lifecycle.state == ApplicationState.RUNNING

    # ------------------------------------------------------------------ #
    # Private Helpers                                                      #
    # ------------------------------------------------------------------ #

    def _handle_bootstrap_failure(self, error: Exception) -> None:
        """Handle errors during bootstrap by executing cleanup before entering FAILED state."""
        self.lifecycle.transition_to(ApplicationState.FAILED)

        # Retrieve event bus if initialized to announce failure
        if self.container:
            try:
                event_bus = self.container.resolve(EventBusPort)
                event_bus.publish(RuntimeFailed(error_message=str(error)))
            except Exception:
                pass

        # Perform cleanup
        self.registry.dispose_all()

        # Transition to STOPPED after cleanup completes
        self.lifecycle.transition_to(ApplicationState.STOPPED)
