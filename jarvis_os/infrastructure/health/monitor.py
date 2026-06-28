"""
Concrete HealthMonitor and health check providers for system infrastructure.

Implements the HealthMonitorPort contract, supporting both the legacy checker callback
registrations and modern HealthProvider implementations. Thread-safe and timeout-bounded.
"""
from dataclasses import dataclass
from datetime import datetime
import threading
from typing import Any, Callable, Dict, List, Optional

from jarvis_os.core.ports.health import HealthMonitorPort, HealthProvider, HealthReport, HealthStatus, SubsystemHealth
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.domain.entities import SubsystemStatus
from jarvis_os.core.domain.value_objects import UserIdentity
from jarvis_os.core.domain.exceptions import SubsystemError
from jarvis_os.infrastructure.database.connection import SQLiteConnectionManager


# ═══════════════════════════════════════════════════════════════════════ #
#  Legacy Adaptor                                                         #
# ═══════════════════════════════════════════════════════════════════════ #

class LegacyHealthProvider(HealthProvider):
    """Bridges legacy Callable[[], SubsystemStatus] checkers to the HealthProvider interface."""

    def __init__(self, name: str, checker: Callable[[], SubsystemStatus]) -> None:
        self._name = name
        self._checker = checker

    @property
    def name(self) -> str:
        return self._name

    def get_health(self) -> SubsystemHealth:
        status = self._checker()
        # Map boolean to HealthStatus
        hs = HealthStatus.HEALTHY if status.is_healthy else HealthStatus.UNHEALTHY
        return SubsystemHealth(
            name=self._name,
            status=hs,
            message=status.message,
            last_checked=status.last_checked,
            details=status.details,
        )


# ═══════════════════════════════════════════════════════════════════════ #
#  Concrete Providers                                                     #
# ═══════════════════════════════════════════════════════════════════════ #

class RuntimeHealthProvider(HealthProvider):
    """Evaluates the health of the Application host runtime lifecycle."""

    def __init__(self, app_host: Any) -> None:
        self.app_host = app_host

    @property
    def name(self) -> str:
        return "Runtime"

    def get_health(self) -> SubsystemHealth:
        # Check host using duck typing to prevent circular dependencies
        try:
            state_val = getattr(self.app_host.lifecycle, "state", None)
            state_name = getattr(state_val, "name", "UNKNOWN")
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Failed to query runtime state: {exc}",
                last_checked=datetime.now(),
            )

        if state_name == "RUNNING":
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Runtime is running normally.",
                last_checked=datetime.now(),
                details={"state": state_name},
            )
        elif state_name in ("BOOTSTRAPPING", "INITIALIZING", "SHUTTING_DOWN", "CONFIG_LOADED", "DI_READY", "INFRASTRUCTURE_READY"):
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.DEGRADED,
                message=f"Runtime is currently transitioning (State: {state_name}).",
                last_checked=datetime.now(),
                details={"state": state_name},
            )
        else:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Runtime lifecycle is stopped or failed (State: {state_name}).",
                last_checked=datetime.now(),
                details={"state": state_name},
            )


class ConfigHealthProvider(HealthProvider):
    """Evaluates the health of the configuration settings module."""

    def __init__(self, config: ConfigurationPort) -> None:
        self.config = config

    @property
    def name(self) -> str:
        return "Configuration"

    def get_health(self) -> SubsystemHealth:
        try:
            # Check basic retrieval and execute port validation rules
            self.config.validate()
            db_path = self.config.get("db.path")
            log_level = self.config.get("log.level")
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Configuration validated successfully.",
                last_checked=datetime.now(),
                details={"db.path": db_path, "log.level": log_level},
            )
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Configuration validation failed: {exc}",
                last_checked=datetime.now(),
            )


class DatabaseHealthProvider(HealthProvider):
    """Evaluates the health of the SQLite connection and journal settings."""

    def __init__(self, db_manager: SQLiteConnectionManager) -> None:
        self.db_manager = db_manager

    @property
    def name(self) -> str:
        return "Database"

    def get_health(self) -> SubsystemHealth:
        try:
            if not self.db_manager.is_open:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection is not open.",
                    last_checked=datetime.now(),
                )

            # Perform a test query and check pragmas
            self.db_manager.execute("SELECT 1;")
            journal_mode = self.db_manager.get_journal_mode()
            fk_enabled = self.db_manager.get_foreign_keys_enabled()

            # Degraded if WAL is configured but not active (e.g. memory databases may fallback)
            status = HealthStatus.HEALTHY
            msg = "Database connection is healthy."
            if journal_mode != "wal" and self.db_manager._db_path != ":memory:":
                status = HealthStatus.DEGRADED
                msg = f"Database is open but journal mode is '{journal_mode}' (expected WAL)."

            return SubsystemHealth(
                name=self.name,
                status=status,
                message=msg,
                last_checked=datetime.now(),
                details={
                    "journal_mode": journal_mode,
                    "foreign_keys_enabled": fk_enabled,
                    "path": self.db_manager._db_path,
                },
            )
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Database health check failed: {exc}",
                last_checked=datetime.now(),
            )


class RepositoryHealthProvider(HealthProvider):
    """Evaluates the health of the Repository schema status."""

    def __init__(self, db_manager: SQLiteConnectionManager) -> None:
        self.db_manager = db_manager

    @property
    def name(self) -> str:
        return "Repository"

    def get_health(self) -> SubsystemHealth:
        try:
            if not self.db_manager.is_open:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message="Database connection is not open, repository cannot function.",
                    last_checked=datetime.now(),
                )

            # Query schema_version table if it exists
            table_row = self.db_manager.fetch_one(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version';"
            )
            if not table_row:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.DEGRADED,
                    message="schema_version table does not exist (migrations not run).",
                    last_checked=datetime.now(),
                )

            # Fetch applied migration count
            count_row = self.db_manager.fetch_one("SELECT COUNT(*) FROM schema_version;")
            count = count_row[0] if count_row else 0

            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message=f"Repository framework is functional. {count} migrations applied.",
                last_checked=datetime.now(),
                details={"applied_migrations": count},
            )
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Repository health check failed: {exc}",
                last_checked=datetime.now(),
            )


class EventBusHealthProvider(HealthProvider):
    """Evaluates the health of the synchronous Event Bus dispatching pipeline."""

    def __init__(self, event_bus: EventBusPort) -> None:
        self.event_bus = event_bus

    @property
    def name(self) -> str:
        return "EventBus"

    def get_health(self) -> SubsystemHealth:
        # Check synchronous publish-subscribe flow
        from jarvis_os.core.domain.events import DomainEvent
        from dataclasses import dataclass

        @dataclass
        class HealthCheckTestEvent(DomainEvent):
            pass

        received = []

        try:
            handler = lambda e: received.append(True)
            self.event_bus.subscribe(HealthCheckTestEvent, handler)
            self.event_bus.publish(HealthCheckTestEvent())
            self.event_bus.unsubscribe(HealthCheckTestEvent, handler)

            if len(received) == 1:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.HEALTHY,
                    message="Event Bus delivery loop is functional.",
                    last_checked=datetime.now(),
                )
            else:
                return SubsystemHealth(
                    name=self.name,
                    status=HealthStatus.UNHEALTHY,
                    message="Event Bus failed to deliver event to subscriber.",
                    last_checked=datetime.now(),
                )
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Event Bus health check failed: {exc}",
                last_checked=datetime.now(),
            )


class PolicyHealthProvider(HealthProvider):
    """Evaluates the health of the Policy Engine access checks."""

    def __init__(self, policy: PolicyPort) -> None:
        self.policy = policy

    @property
    def name(self) -> str:
        return "Policy"

    def get_health(self) -> SubsystemHealth:
        try:
            # Perform basic path check and authorization checks
            self.policy.validate_path("/some/sandbox/path")

            dummy_user = UserIdentity("dummy", roles=["admin"])
            # Simple check that shouldn't crash
            self.policy.is_authorized(dummy_user, "read", "sys:config")

            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.HEALTHY,
                message="Policy engine validations are functional.",
                last_checked=datetime.now(),
            )
        except Exception as exc:
            return SubsystemHealth(
                name=self.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Policy engine health check failed: {exc}",
                last_checked=datetime.now(),
            )


# ═══════════════════════════════════════════════════════════════════════ #
#  Health Monitor implementation                                          #
# ═══════════════════════════════════════════════════════════════════════ #

class HealthMonitor(HealthMonitorPort):
    """Coordinates and aggregates subsystem health checking with timeouts."""

    def __init__(self) -> None:
        self._providers: Dict[str, HealthProvider] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # HealthMonitorPort Implementation                                     #
    # ------------------------------------------------------------------ #

    def register_provider(self, provider: HealthProvider) -> None:
        """Register a modern HealthProvider."""
        with self._lock:
            self._providers[provider.name] = provider

    def register_subsystem(self, name: str, checker: Callable[[], SubsystemStatus]) -> None:
        """Legacy port integration: register checker callback as LegacyHealthProvider."""
        with self._lock:
            self.register_provider(LegacyHealthProvider(name, checker))

    def check_subsystem(self, name: str) -> SubsystemStatus:
        """Check a single subsystem's health by name (timeout-bounded)."""
        with self._lock:
            provider = self._providers.get(name)
            if not provider:
                raise SubsystemError(f"Subsystem '{name}' is not registered with the health monitor.")

        sub_health = self._evaluate_with_timeout(provider, timeout=2.0)
        return self._map_to_legacy_status(sub_health)

    def check_health(self) -> List[SubsystemStatus]:
        """Aggregate health from all subsystems (returns legacy List[SubsystemStatus])."""
        report = self.get_health_report(timeout=2.0)
        return [self._map_to_legacy_status(sh) for sh in report.subsystems]

    def get_health_report(self, timeout: float = 2.0) -> HealthReport:
        """Collect and evaluate all registered HealthProviders into an aggregated HealthReport."""
        with self._lock:
            providers = list(self._providers.values())

        subsystems_health: List[SubsystemHealth] = []
        overall_status = HealthStatus.HEALTHY

        for provider in providers:
            # Continues evaluating remaining providers even if one fails or times out
            sub_health = self._evaluate_with_timeout(provider, timeout=timeout)
            subsystems_health.append(sub_health)

            # Accumulator status mapping: UNHEALTHY takes priority over DEGRADED, which overrides HEALTHY
            if sub_health.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif sub_health.status == HealthStatus.DEGRADED and overall_status != HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.DEGRADED

        return HealthReport(
            overall_status=overall_status,
            checked_at=datetime.now(),
            subsystems=subsystems_health,
        )

    # ------------------------------------------------------------------ #
    # Private Helpers                                                      #
    # ------------------------------------------------------------------ #

    def _evaluate_with_timeout(self, provider: HealthProvider, timeout: float) -> SubsystemHealth:
        """Execute a provider's get_health() call in a daemon thread with timeout."""
        result: List[SubsystemHealth] = []
        errors: List[Exception] = []

        def worker():
            try:
                result.append(provider.get_health())
            except Exception as exc:
                errors.append(exc)

        thread = threading.Thread(target=worker)
        thread.daemon = True
        thread.start()
        thread.join(timeout=timeout)

        if thread.is_alive():
            return SubsystemHealth(
                name=provider.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check timed out after {timeout} seconds.",
                last_checked=datetime.now(),
            )

        if errors:
            return SubsystemHealth(
                name=provider.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Health check threw exception: {errors[0]}",
                last_checked=datetime.now(),
            )

        return result[0]

    def _map_to_legacy_status(self, sh: SubsystemHealth) -> SubsystemStatus:
        """Convert a SubsystemHealth object to the legacy SubsystemStatus entity."""
        return SubsystemStatus(
            name=sh.name,
            is_healthy=(sh.status != HealthStatus.UNHEALTHY),
            message=sh.message,
            last_checked=sh.last_checked,
            details=sh.details,
        )
