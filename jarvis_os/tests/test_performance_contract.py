"""
Contract Test for PerformanceMonitorPort.
"""
import unittest
import contextlib
from datetime import datetime
from typing import Any, List, Optional
from jarvis_os.core.ports.performance import PerformanceMonitorPort
from jarvis_os.core.domain.value_objects import SystemResourceUsage
from jarvis_os.core.domain.entities import MetricSample

class TestPerformanceMonitorPortContract(unittest.TestCase):
    """Verifies that the PerformanceMonitorPort interface conforms to design specifications."""

    def test_interface_is_abstract(self):
        """Asserts that the PerformanceMonitorPort cannot be directly instantiated."""
        with self.assertRaises(TypeError):
            PerformanceMonitorPort()  # type: ignore

    def test_concrete_subclass_enforcement(self):
        """Asserts that subclassing requires implementing all abstract methods."""
        class IncompletePerformance(PerformanceMonitorPort):
            pass

        with self.assertRaises(TypeError):
            IncompletePerformance()  # type: ignore

    def test_valid_implementation_signatures(self):
        """Asserts that a fully-conforming mock subclass can be instantiated."""
        class MockPerformance(PerformanceMonitorPort):
            def __init__(self):
                self._metrics = []

            def get_resource_usage(self) -> SystemResourceUsage:
                return SystemResourceUsage(
                    cpu_percent=12.5,
                    ram_used_bytes=2147483648,
                    ram_total_bytes=8589934592,
                    disk_used_bytes=53687091200,
                    disk_free_bytes=26843545600
                )

            def record_metric(self, metric: MetricSample) -> None:
                self._metrics.append(metric)

            def get_metrics(self, metric_name: Optional[str] = None) -> List[MetricSample]:
                if metric_name:
                    return [m for m in self._metrics if m.name == metric_name]
                return self._metrics

            @contextlib.contextmanager
            def measure_latency(self, operation_name: str) -> Any:
                start = datetime.now()
                yield
                elapsed = (datetime.now() - start).total_seconds()
                self.record_metric(MetricSample(
                    name=f"{operation_name}_latency",
                    value=elapsed,
                    unit="seconds",
                    timestamp=datetime.now()
                ))

        monitor = MockPerformance()
        self.assertIsInstance(monitor, PerformanceMonitorPort)
        
        # Test resource usage
        usage = monitor.get_resource_usage()
        self.assertIsInstance(usage, SystemResourceUsage)
        self.assertEqual(usage.cpu_percent, 12.5)
        
        # Test metric recording
        sample = MetricSample(name="memory_footprint", value=20.0, unit="MB", timestamp=datetime.now())
        monitor.record_metric(sample)
        self.assertEqual(monitor.get_metrics("memory_footprint"), [sample])
        
        # Test latency profiling context manager contract
        with monitor.measure_latency("test_op"):
            pass
            
        latency_metrics = monitor.get_metrics("test_op_latency")
        self.assertEqual(len(latency_metrics), 1)
        self.assertEqual(latency_metrics[0].unit, "seconds")

if __name__ == "__main__":
    unittest.main()
