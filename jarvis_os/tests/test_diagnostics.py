"""
Unit tests for the Developer Diagnostics subsystem.
"""
from datetime import datetime
import threading
import time
import unittest
from typing import Any, Dict, List, Optional

from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.ports.runtime import RuntimePort
from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.ports.health import (
    HealthMonitorPort,
    HealthReport,
    HealthStatus,
    SubsystemHealth,
)
from jarvis_os.core.ports.performance import PerformanceMonitorPort
from jarvis_os.core.ports.diagnostics import (
    DiagnosticProvider,
    DiagnosticsReport,
)
from jarvis_os.core.domain.value_objects import SystemResourceUsage
from jarvis_os.core.domain.entities import MetricSample
from jarvis_os.infrastructure.diagnostics.service import DiagnosticsService


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock Implementations for Test Isolation                                #
# ═══════════════════════════════════════════════════════════════════════ #

class MockConfig(ConfigurationPort):
    def __init__(self, valid: bool = True, raise_on_validate: bool = False) -> None:
        self._valid = valid
        self._raise_on_validate = raise_on_validate

    def get(self, key: str, default: Any = None) -> Any:
        if key == "jarvis.version":
            return "1.5.0"
        return default

    def get_boolean(self, key: str, default: bool = False) -> bool:
        return default

    def get_int(self, key: str, default: int = 0) -> int:
        return default

    def get_string(self, key: str, default: str = "") -> str:
        return default

    def set(self, key: str, value: Any) -> None:
        pass

    def load(self) -> None:
        pass

    def validate(self) -> bool:
        if self._raise_on_validate:
            raise ValueError("Schema validation failed: missing database path")
        return self._valid

    def get_all(self) -> Dict[str, Any]:
        return {}


class MockRuntime(RuntimePort):
    def __init__(self, state_name: str = "RUNNING", services: Optional[List[str]] = None) -> None:
        self.state_name = state_name
        self.services = services or ["config", "logger", "database"]
        # Nested class mock for application state / lifecycle
        class DummyState:
            def __init__(self, name: str) -> None:
                self.name = name
        class DummyLifecycle:
            def __init__(self, name: str) -> None:
                self.state = DummyState(name)
        class DummyRegistry:
            def __init__(self, services: List[str]) -> None:
                self._services = services
            def list_services(self) -> List[str]:
                return self._services

        self.lifecycle = DummyLifecycle(state_name)
        self.registry = DummyRegistry(self.services)

    def bootstrap(self) -> None:
        pass

    def shutdown(self) -> None:
        pass

    def is_running(self) -> bool:
        return self.state_name == "RUNNING"


class MockDatabaseManager:
    def __init__(self, is_open: bool = True, raise_on_query: bool = False) -> None:
        self._is_open = is_open
        self._raise_on_query = raise_on_query
        self._db_path = "test_jarvis.db"

    @property
    def is_open(self) -> bool:
        return self._is_open

    def fetch_one(self, sql: str, params: tuple = ()) -> Optional[tuple]:
        if self._raise_on_query:
            raise RuntimeError("Database connection timed out or is locked")
        if sql == "PRAGMA schema_version":
            return (42,)
        return None


class MockEventBus(EventBusPort):
    def __init__(self, subscribers_dict: Optional[dict] = None) -> None:
        self._subscribers = subscribers_dict or {}

    def subscribe(self, event_type: Any, handler: Any) -> None:
        pass

    def unsubscribe(self, event_type: Any, handler: Any) -> None:
        pass

    def publish(self, event: Any) -> None:
        pass


class MockPolicyEngine(PolicyPort):
    def __init__(self, rules_count: int = 5) -> None:
        # Dummy lists matching policy engine private fields
        class DummyRule:
            def __init__(self) -> None:
                self.priority = 0
                self.name = "Rule"
        self._rules = [DummyRule() for _ in range(rules_count)]
        self._path_permissions = ["/sandbox/read", "/sandbox/write"]
        self._command_definitions = ["git", "python"]

    def is_authorized(self, user: Any, action: str, resource: str) -> bool:
        return True

    def validate_path(self, target_path: str) -> bool:
        return True

    def validate_command(self, command_line: str) -> bool:
        return True



class MockHealthMonitor(HealthMonitorPort):
    def __init__(self, status: HealthStatus = HealthStatus.HEALTHY, raise_on_report: bool = False) -> None:
        self.status = status
        self.raise_on_report = raise_on_report

    def check_health(self) -> List[Any]:
        return []

    def check_subsystem(self, name: str) -> Any:
        return None

    def register_subsystem(self, name: str, checker: Any) -> None:
        pass

    def register_provider(self, provider: Any) -> None:
        pass

    def get_health_report(self, timeout: float = 2.0) -> HealthReport:
        if self.raise_on_report:
            raise RuntimeError("Subsystem checks timed out")
        return HealthReport(
            overall_status=self.status,
            checked_at=datetime.now(),
            subsystems=[
                SubsystemHealth("Database", self.status, "Status description", datetime.now()),
                SubsystemHealth("Policy", HealthStatus.HEALTHY, "Rules loaded", datetime.now()),
            ]
        )


class MockPerformanceMonitor(PerformanceMonitorPort):
    def __init__(self, raise_on_usage: bool = False) -> None:
        self.raise_on_usage = raise_on_usage

    def get_resource_usage(self) -> SystemResourceUsage:
        if self.raise_on_usage:
            raise RuntimeError("System resource sampling failed")
        return SystemResourceUsage(
            cpu_percent=15.5,
            ram_used_bytes=1024 * 1024 * 512,
            ram_total_bytes=1024 * 1024 * 1024 * 8,
            disk_used_bytes=1024 * 1024 * 1024 * 10,
            disk_free_bytes=1024 * 1024 * 1024 * 90,
        )

    def record_metric(self, metric: MetricSample) -> None:
        pass

    def get_metrics(self, metric_name: Optional[str] = None) -> List[MetricSample]:
        return [
            MetricSample("db_latency", 0.05, "seconds", datetime.now()),
            MetricSample("ram_usage", 512.0, "MB", datetime.now()),
        ]

    import contextlib
    @contextlib.contextmanager
    def measure_latency(self, operation_name: str) -> Any:
        yield

    def get_performance_snapshot(self) -> Any:
        # Mimic the concrete implementation
        class DummySnapshot:
            def __init__(self) -> None:
                self.metrics = [
                    MetricSample("db_latency", 0.05, "seconds", datetime.now()),
                    MetricSample("ram_usage", 512.0, "MB", datetime.now()),
                ]
        return DummySnapshot()


class SimpleDiagnosticProvider(DiagnosticProvider):
    def __init__(self, name: str, details: dict) -> None:
        self._name = name
        self.details = details

    @property
    def name(self) -> str:
        return self._name

    def get_diagnostics(self) -> Dict[str, Any]:
        return self.details


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Cases                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestDeveloperDiagnostics(unittest.TestCase):
    """Tests diagnostics service read-only aggregation, safety, and correctness."""

    def test_successful_diagnostics_generation(self) -> None:
        """Verify that a successful aggregation maps all subsystem details correctly."""
        service = DiagnosticsService(
            config=MockConfig(valid=True),
            runtime=MockRuntime(state_name="RUNNING"),
            db_manager=MockDatabaseManager(is_open=True),
            event_bus=MockEventBus(subscribers_dict={str: [lambda x: None]}),
            policy_engine=MockPolicyEngine(rules_count=3),
            health_monitor=MockHealthMonitor(status=HealthStatus.HEALTHY),
            performance_monitor=MockPerformanceMonitor(),
        )

        # Register custom provider
        custom_prov = SimpleDiagnosticProvider("CustomTelemetry", {"uptime_seconds": 3600})
        service.register_provider(custom_prov)

        report = service.get_diagnostics_report()

        # Check general constraints
        self.assertIsInstance(report, DiagnosticsReport)
        self.assertEqual(report.overall_status, "HEALTHY")
        self.assertEqual(report.runtime_state, "RUNNING")
        self.assertEqual(report.config_status.get("valid"), True)
        self.assertEqual(report.database_status.get("connected"), True)
        self.assertEqual(report.database_status.get("schema_version"), 42)
        
        # Health & Performance summaries
        self.assertEqual(report.health_summary.get("status"), "HEALTHY")
        self.assertEqual(len(report.health_summary.get("subsystems", [])), 2)
        self.assertEqual(report.performance_summary.get("cpu_percent"), 15.5)
        self.assertEqual(report.performance_summary.get("metric_count"), 2)

        # Environment
        self.assertTrue(len(report.python_version) > 0)
        self.assertTrue(len(report.platform_information) > 0)

        # Custom Provider
        self.assertEqual(report.extra_details.get("CustomTelemetry"), {"uptime_seconds": 3600})

        # Test human readable format
        text = DiagnosticsService.format_report_to_human_readable(report)
        self.assertIn("Timestamp:", text)
        self.assertIn("Overall Status:        HEALTHY", text)
        self.assertIn("CPU Utilization:     15.5%", text)
        self.assertIn("CustomTelemetry", text)

    def test_unhealthy_subsystem_reporting(self) -> None:
        """Verify overall status reflects UNHEALTHY if health monitor reports unhealthy status."""
        service = DiagnosticsService(
            config=MockConfig(),
            runtime=MockRuntime(),
            db_manager=MockDatabaseManager(),
            health_monitor=MockHealthMonitor(status=HealthStatus.UNHEALTHY),
        )
        report = service.get_diagnostics_report()
        self.assertEqual(report.overall_status, "UNHEALTHY")
        self.assertEqual(report.health_summary.get("status"), "UNHEALTHY")

    def test_degraded_subsystem_reporting(self) -> None:
        """Verify overall status reflects DEGRADED if health monitor reports degraded status."""
        service = DiagnosticsService(
            config=MockConfig(),
            runtime=MockRuntime(),
            db_manager=MockDatabaseManager(),
            health_monitor=MockHealthMonitor(status=HealthStatus.DEGRADED),
        )
        report = service.get_diagnostics_report()
        self.assertEqual(report.overall_status, "DEGRADED")
        self.assertEqual(report.health_summary.get("status"), "DEGRADED")

    def test_missing_services(self) -> None:
        """Verify diagnostics handles None values for services safely without crashing."""
        service = DiagnosticsService()
        report = service.get_diagnostics_report()
        
        self.assertEqual(report.overall_status, "UNHEALTHY")  # Config and database missing means unhealthy
        self.assertEqual(report.runtime_state, "MISSING")
        self.assertEqual(report.config_status.get("valid"), False)
        self.assertEqual(report.database_status.get("connected"), False)
        self.assertEqual(report.event_bus_status.get("available"), False)
        self.assertEqual(report.policy_engine_status.get("available"), False)
        self.assertEqual(report.health_summary.get("status"), "UNKNOWN")

    def test_configuration_validation_failures(self) -> None:
        """Verify config_status correctly reports when validation raises exception."""
        service = DiagnosticsService(
            config=MockConfig(raise_on_validate=True),
        )
        report = service.get_diagnostics_report()
        self.assertEqual(report.config_status.get("valid"), False)
        self.assertIn("Schema validation failed", report.config_status.get("error", ""))

    def test_database_unavailable(self) -> None:
        """Verify database connectedness reporting when connection is closed or query fails."""
        # 1. Closed connection case
        service_closed = DiagnosticsService(
            db_manager=MockDatabaseManager(is_open=False)
        )
        report_closed = service_closed.get_diagnostics_report()
        self.assertEqual(report_closed.database_status.get("connected"), False)
        self.assertEqual(report_closed.database_status.get("open"), False)

        # 2. Open but throwing queries case
        service_faulty = DiagnosticsService(
            db_manager=MockDatabaseManager(is_open=True, raise_on_query=True)
        )
        report_faulty = service_faulty.get_diagnostics_report()
        self.assertEqual(report_faulty.database_status.get("connected"), False)
        self.assertEqual(report_faulty.database_status.get("open"), True)
        self.assertIn("Database connection timed out", report_faulty.database_status.get("error", ""))

    def test_health_monitor_timeout_or_error_handling(self) -> None:
        """Verify that health monitoring evaluation crashes are caught safely."""
        service = DiagnosticsService(
            health_monitor=MockHealthMonitor(raise_on_report=True)
        )
        report = service.get_diagnostics_report()
        self.assertEqual(report.health_summary.get("status"), "ERROR")
        self.assertEqual(report.overall_status, "UNHEALTHY")
        self.assertIn("Subsystem checks timed out", report.health_summary.get("error", ""))

    def test_performance_monitor_errors(self) -> None:
        """Verify that performance monitor sampling crashes do not abort overall report."""
        service = DiagnosticsService(
            config=MockConfig(),
            performance_monitor=MockPerformanceMonitor(raise_on_usage=True)
        )
        report = service.get_diagnostics_report()
        self.assertIn("System resource sampling failed", report.performance_summary.get("resource_usage_error", ""))

    def test_report_immutability(self) -> None:
        """Verify that the DiagnosticsReport model properties are frozen and cannot be changed."""
        report = DiagnosticsReport(
            timestamp=datetime.now(),
            overall_status="HEALTHY",
            runtime_state="RUNNING",
            config_status={},
            database_status={},
            health_summary={},
            performance_summary={},
            registered_services=[],
            event_bus_status={},
            policy_engine_status={},
            environment_information={},
            python_version="3.11",
            platform_information="Windows",
        )
        with self.assertRaises(AttributeError):
            report.overall_status = "UNHEALTHY"  # type: ignore

        with self.assertRaises(AttributeError):
            report.new_field = "test"  # type: ignore

    def test_thread_safety_concurrent_diagnostics(self) -> None:
        """Verify concurrent requests and registration perform correctly without race conditions."""
        service = DiagnosticsService(
            config=MockConfig(),
            runtime=MockRuntime(),
            db_manager=MockDatabaseManager(),
        )

        barrier = threading.Barrier(10)

        def worker(idx: int) -> None:
            barrier.wait()
            # Register a provider
            service.register_provider(SimpleDiagnosticProvider(f"Prov_{idx}", {"idx": idx}))
            # Generate report
            report = service.get_diagnostics_report()
            self.assertIsInstance(report, DiagnosticsReport)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_report = service.get_diagnostics_report()
        # Verify 10 providers got registered successfully
        self.assertEqual(len(final_report.extra_details), 10)


if __name__ == "__main__":
    unittest.main()
