"""
Contract Test for HealthMonitorPort.
"""
import unittest
from datetime import datetime
from typing import Callable, List
from jarvis_os.core.ports.health import HealthMonitorPort
from jarvis_os.core.domain.entities import SubsystemStatus
from jarvis_os.core.domain.exceptions import SubsystemError

class TestHealthMonitorPortContract(unittest.TestCase):
    """Verifies that the HealthMonitorPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the HealthMonitorPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            HealthMonitorPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompleteHealth(HealthMonitorPort):
            pass

        with self.assertRaises(TypeError):
            IncompleteHealth()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockHealth(HealthMonitorPort):
            def __init__(self):
                self._checkers = {}

            def check_health(self) -> List[SubsystemStatus]:
                return [check_fn() for check_fn in self._checkers.values()]

            def check_subsystem(self, name: str) -> SubsystemStatus:
                if name not in self._checkers:
                    raise SubsystemError(f"Subsystem {name} not found")
                return self._checkers[name]()

            def register_subsystem(self, name: str, checker: Callable[[], SubsystemStatus]) -> None:
                self._checkers[name] = checker

        health = MockHealth()
        self.assertIsInstance(health, HealthMonitorPort)
        
        status_db = SubsystemStatus(name="Database", is_healthy=True, message="Connected", last_checked=datetime.now())
        health.register_subsystem("Database", lambda: status_db)
        
        self.assertEqual(health.check_subsystem("Database"), status_db)
        self.assertEqual(health.check_health(), [status_db])
        
        with self.assertRaises(SubsystemError):
            health.check_subsystem("Voice")

if __name__ == "__main__":
    unittest.main()
