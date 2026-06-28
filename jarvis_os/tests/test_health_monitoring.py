"""
Unit tests for the Health Monitoring subsystem.
"""
from datetime import datetime
import time
import threading
import unittest
from typing import Any, Dict, List, Optional

from jarvis_os.core.ports.health import HealthProvider, HealthReport, HealthStatus, SubsystemHealth
from jarvis_os.core.domain.entities import SubsystemStatus
from jarvis_os.core.domain.exceptions import SubsystemError
from jarvis_os.infrastructure.health.monitor import (
    HealthMonitor,
    LegacyHealthProvider,
)


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock Providers                                                         #
# ═══════════════════════════════════════════════════════════════════════ #

class SimpleMockProvider(HealthProvider):
    """Mock provider with configurable state."""

    def __init__(self, name: str, status: HealthStatus, message: str = "") -> None:
        self._name = name
        self.status = status
        self.message = message

    @property
    def name(self) -> str:
        return self._name

    def get_health(self) -> SubsystemHealth:
        return SubsystemHealth(
            name=self._name,
            status=self.status,
            message=self.message,
            last_checked=datetime.now(),
        )


class SlowMockProvider(HealthProvider):
    """Mock provider that blocks to simulate timeout conditions."""

    def __init__(self, name: str, delay: float) -> None:
        self._name = name
        self.delay = delay

    @property
    def name(self) -> str:
        return self._name

    def get_health(self) -> SubsystemHealth:
        time.sleep(self.delay)
        return SubsystemHealth(
            name=self._name,
            status=HealthStatus.HEALTHY,
            message="Delayed success",
            last_checked=datetime.now(),
        )


class FaultyMockProvider(HealthProvider):
    """Mock provider that throws exceptions."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get_health(self) -> SubsystemHealth:
        raise ValueError("Simulated check crash")


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Suite                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestHealthMonitoring(unittest.TestCase):
    """Tests verify enums, aggregation logic, timeout isolation, and concurrency safety."""

    def setUp(self) -> None:
        self.monitor = HealthMonitor()

    # ------------------------------------------------------------------ #
    # Basic Checks                                                         #
    # ------------------------------------------------------------------ #

    def test_healthy_provider_evaluation(self) -> None:
        """Provider returning HEALTHY behaves correctly."""
        p = SimpleMockProvider("Test", HealthStatus.HEALTHY, "Normal")
        self.monitor.register_provider(p)

        report = self.monitor.get_health_report()
        self.assertEqual(report.overall_status, HealthStatus.HEALTHY)
        self.assertEqual(len(report.subsystems), 1)
        self.assertEqual(report.subsystems[0].name, "Test")
        self.assertEqual(report.subsystems[0].status, HealthStatus.HEALTHY)

    def test_degraded_provider_evaluation(self) -> None:
        """Provider returning DEGRADED behaves correctly."""
        p = SimpleMockProvider("Test", HealthStatus.DEGRADED, "Warning")
        self.monitor.register_provider(p)

        report = self.monitor.get_health_report()
        self.assertEqual(report.overall_status, HealthStatus.DEGRADED)
        self.assertEqual(report.subsystems[0].status, HealthStatus.DEGRADED)

    def test_unhealthy_provider_evaluation(self) -> None:
        """Provider returning UNHEALTHY behaves correctly."""
        p = SimpleMockProvider("Test", HealthStatus.UNHEALTHY, "Critical")
        self.monitor.register_provider(p)

        report = self.monitor.get_health_report()
        self.assertEqual(report.overall_status, HealthStatus.UNHEALTHY)
        self.assertEqual(report.subsystems[0].status, HealthStatus.UNHEALTHY)

    # ------------------------------------------------------------------ #
    # Timeout Handling                                                     #
    # ------------------------------------------------------------------ #

    def test_timeout_handling_returns_deterministic_unhealthy(self) -> None:
        """If check exceeds timeout, it is terminated and reported as UNHEALTHY."""
        p = SlowMockProvider("Slow", delay=1.0)
        self.monitor.register_provider(p)

        # Evaluate with 0.1s timeout limit
        report = self.monitor.get_health_report(timeout=0.1)
        self.assertEqual(report.overall_status, HealthStatus.UNHEALTHY)
        self.assertEqual(report.subsystems[0].name, "Slow")
        self.assertEqual(report.subsystems[0].status, HealthStatus.UNHEALTHY)
        self.assertIn("timed out", report.subsystems[0].message)

    # ------------------------------------------------------------------ #
    # Exception Handling                                                   #
    # ------------------------------------------------------------------ #

    def test_exception_handling_isolation(self) -> None:
        """If a provider check throws, the monitor continues and marks it UNHEALTHY."""
        p1 = FaultyMockProvider("Faulty")
        p2 = SimpleMockProvider("Healthy", HealthStatus.HEALTHY, "OK")

        self.monitor.register_provider(p1)
        self.monitor.register_provider(p2)

        report = self.monitor.get_health_report()

        # Overall must be UNHEALTHY due to Faulty
        self.assertEqual(report.overall_status, HealthStatus.UNHEALTHY)

        sub_states = {sh.name: sh.status for sh in report.subsystems}
        self.assertEqual(sub_states["Faulty"], HealthStatus.UNHEALTHY)
        self.assertEqual(sub_states["Healthy"], HealthStatus.HEALTHY)

    # ------------------------------------------------------------------ #
    # Aggregation Logic                                                    #
    # ------------------------------------------------------------------ #

    def test_empty_provider_list(self) -> None:
        """Empty providers evaluates overall as HEALTHY."""
        report = self.monitor.get_health_report()
        self.assertEqual(report.overall_status, HealthStatus.HEALTHY)
        self.assertEqual(len(report.subsystems), 0)

    def test_status_precedence_accumulation(self) -> None:
        """Overall status follows precedence: UNHEALTHY > DEGRADED > HEALTHY."""
        # Case A: Degraded + Healthy = Degraded
        m1 = HealthMonitor()
        m1.register_provider(SimpleMockProvider("p1", HealthStatus.HEALTHY))
        m1.register_provider(SimpleMockProvider("p2", HealthStatus.DEGRADED))
        self.assertEqual(m1.get_health_report().overall_status, HealthStatus.DEGRADED)

        # Case B: Unhealthy + Degraded + Healthy = Unhealthy
        m2 = HealthMonitor()
        m2.register_provider(SimpleMockProvider("p1", HealthStatus.HEALTHY))
        m2.register_provider(SimpleMockProvider("p2", HealthStatus.DEGRADED))
        m2.register_provider(SimpleMockProvider("p3", HealthStatus.UNHEALTHY))
        self.assertEqual(m2.get_health_report().overall_status, HealthStatus.UNHEALTHY)

    # ------------------------------------------------------------------ #
    # Legacy Port Support                                                  #
    # ------------------------------------------------------------------ #

    def test_legacy_checker_registration_and_checking(self) -> None:
        """Legacy check methods are bridged and resolve safely."""
        legacy_checker = lambda: SubsystemStatus(
            name="legacy",
            is_healthy=False,
            message="Degraded database status",
            last_checked=datetime.now(),
        )

        self.monitor.register_subsystem("legacy", legacy_checker)

        # Check legacy method output
        status = self.monitor.check_subsystem("legacy")
        self.assertEqual(status.name, "legacy")
        self.assertFalse(status.is_healthy)
        self.assertEqual(status.message, "Degraded database status")

    def test_unregistered_subsystem_raises_error(self) -> None:
        """Querying unregistered legacy subsystems raises SubsystemError."""
        with self.assertRaises(SubsystemError):
            self.monitor.check_subsystem("missing")

    # ------------------------------------------------------------------ #
    # Thread Safety                                                         #
    # ------------------------------------------------------------------ #

    def test_health_checking_is_thread_safe(self) -> None:
        """Subsystem registrations and reports are safe from concurrent state issues."""
        errors = []

        def worker(thread_idx: int) -> None:
            try:
                for i in range(20):
                    p = SimpleMockProvider(
                        name=f"T{thread_idx}_P{i}",
                        status=HealthStatus.HEALTHY,
                    )
                    self.monitor.register_provider(p)
                    report = self.monitor.get_health_report()
                    self.assertEqual(report.overall_status, HealthStatus.HEALTHY)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
