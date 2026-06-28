"""
Unit tests for the Performance Monitoring subsystem in Jarvis OS.
"""
from datetime import datetime
import threading
import time
import unittest
from typing import List

from jarvis_os.core.ports.performance import (
    PerformanceMonitorPort,
    PerformanceProvider,
    PerformanceSnapshot,
)
from jarvis_os.core.domain.value_objects import SystemResourceUsage
from jarvis_os.core.domain.entities import MetricSample
from jarvis_os.infrastructure.performance.monitor import (
    PerformanceMonitor,
    SystemResourceSampler,
)


# ═══════════════════════════════════════════════════════════════════════ #
#  Mock Performance Providers                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class SimpleMockProvider(PerformanceProvider):
    """Mock performance provider returning a configured list of metrics."""

    def __init__(self, name: str, metrics: List[MetricSample]) -> None:
        self._name = name
        self.metrics = metrics

    @property
    def name(self) -> str:
        return self._name

    def get_metrics(self) -> List[MetricSample]:
        return self.metrics


class FaultyMockProvider(PerformanceProvider):
    """Mock performance provider that raises an exception during collection."""

    def __init__(self, name: str) -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def get_metrics(self) -> List[MetricSample]:
        raise RuntimeError("Simulated telemetry failure")


# ═══════════════════════════════════════════════════════════════════════ #
#  Test Suite                                                             #
# ═══════════════════════════════════════════════════════════════════════ #

class TestPerformanceMonitoring(unittest.TestCase):
    """Verifies resource sampling, metric storage, latency context, and provider aggregation."""

    def setUp(self) -> None:
        self.monitor = PerformanceMonitor()

    def test_resource_usage_sampling(self) -> None:
        """Verify get_resource_usage returns realistic metrics on active CPU, RAM, and Disk."""
        usage = self.monitor.get_resource_usage()
        self.assertIsInstance(usage, SystemResourceUsage)
        self.assertTrue(0.0 <= usage.cpu_percent <= 100.0)
        self.assertTrue(usage.ram_total_bytes > 0)
        self.assertTrue(usage.ram_used_bytes >= 0)
        self.assertTrue(usage.disk_used_bytes >= 0)
        self.assertTrue(usage.disk_free_bytes >= 0)

    def test_record_and_get_metrics(self) -> None:
        """Verify metric samples are correctly stored and retrieved, supporting name filtering."""
        metric1 = MetricSample(
            name="db_query_time",
            value=0.15,
            unit="seconds",
            timestamp=datetime.now(),
        )
        metric2 = MetricSample(
            name="memory_growth",
            value=45.0,
            unit="MB",
            timestamp=datetime.now(),
        )

        self.monitor.record_metric(metric1)
        self.monitor.record_metric(metric2)

        # Retrieve all
        all_metrics = self.monitor.get_metrics()
        self.assertEqual(len(all_metrics), 2)
        self.assertIn(metric1, all_metrics)
        self.assertIn(metric2, all_metrics)

        # Filter by name
        filtered = self.monitor.get_metrics("db_query_time")
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0], metric1)

        # Non-matching name filter
        self.assertEqual(len(self.monitor.get_metrics("non_existent")), 0)

    def test_measure_latency_context_manager(self) -> None:
        """Verify latency profiling context manager records metrics correctly."""
        with self.monitor.measure_latency("test_calculation"):
            time.sleep(0.05)

        metrics = self.monitor.get_metrics("test_calculation_latency")
        self.assertEqual(len(metrics), 1)
        self.assertEqual(metrics[0].unit, "seconds")
        self.assertTrue(metrics[0].value >= 0.04)

    def test_provider_registration_and_snapshot_aggregation(self) -> None:
        """Verify telemetry snapshot combines monitor metrics and registered providers."""
        # 1. Log an internal metric
        internal_metric = MetricSample(
            name="event_bus_latency",
            value=0.002,
            unit="seconds",
            timestamp=datetime.now(),
        )
        self.monitor.record_metric(internal_metric)

        # 2. Register mock provider
        provider_metric = MetricSample(
            name="sqlite_connections",
            value=3.0,
            unit="count",
            timestamp=datetime.now(),
        )
        provider = SimpleMockProvider("DatabaseSubsystem", [provider_metric])
        self.monitor.register_provider(provider)

        # 3. Request snapshot
        snapshot = self.monitor.get_performance_snapshot()
        self.assertIsInstance(snapshot, PerformanceSnapshot)
        self.assertIsInstance(snapshot.timestamp, datetime)
        
        # Verify both metrics are present
        metric_names = [m.name for m in snapshot.metrics]
        self.assertIn("event_bus_latency", metric_names)
        self.assertIn("sqlite_connections", metric_names)

    def test_faulty_provider_isolation(self) -> None:
        """Verify that provider failure does not abort snapshot aggregation."""
        # 1. Register a good provider
        good_metric = MetricSample(
            name="active_threads",
            value=10.0,
            unit="count",
            timestamp=datetime.now(),
        )
        good_provider = SimpleMockProvider("ThreadsSubsystem", [good_metric])
        self.monitor.register_provider(good_provider)

        # 2. Register a faulty provider
        faulty_provider = FaultyMockProvider("FaultySubsystem")
        self.monitor.register_provider(faulty_provider)

        # 3. Aggregate snapshot
        snapshot = self.monitor.get_performance_snapshot()
        self.assertIsInstance(snapshot, PerformanceSnapshot)

        # 4. Verify good metrics are present
        metric_names = [m.name for m in snapshot.metrics]
        self.assertIn("active_threads", metric_names)

        # 5. Verify exception was recorded as a failure metric
        self.assertIn("FaultySubsystem_provider_failure", metric_names)
        fail_metric = next(m for m in snapshot.metrics if m.name == "FaultySubsystem_provider_failure")
        self.assertEqual(fail_metric.value, 1.0)
        self.assertEqual(fail_metric.unit, "count")
        self.assertIn("metadata", dir(fail_metric))
        if fail_metric.metadata:
            self.assertIn("Simulated telemetry failure", fail_metric.metadata.get("error", ""))

    def test_thread_safety_concurrency(self) -> None:
        """Verify PerformanceMonitor registry functions safely under concurrent access."""
        thread_count = 10
        iterations = 50
        barrier = threading.Barrier(thread_count)

        def worker(thread_idx: int) -> None:
            barrier.wait()
            for i in range(iterations):
                # 1. Record custom metric
                self.monitor.record_metric(MetricSample(
                    name=f"thread_{thread_idx}_metric",
                    value=float(i),
                    unit="count",
                    timestamp=datetime.now(),
                ))
                # 2. Measure block latency
                with self.monitor.measure_latency(f"thread_{thread_idx}_op"):
                    pass
                # 3. Retrieve snapshot
                _ = self.monitor.get_performance_snapshot()

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(thread_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Total metrics recorded should match expectations
        # For each thread: iterations * 2 (1 custom metric + 1 latency metric)
        expected_metrics = thread_count * iterations * 2
        all_metrics = self.monitor.get_metrics()
        self.assertEqual(len(all_metrics), expected_metrics)


if __name__ == "__main__":
    unittest.main()
