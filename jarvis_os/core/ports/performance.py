"""
Performance Monitor Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Any, List, Optional
from jarvis_os.core.domain.value_objects import SystemResourceUsage
from jarvis_os.core.domain.entities import MetricSample

class PerformanceMonitorPort(ABC):
    """Interface defining system resource metrics logging and latency profiling."""

    @abstractmethod
    def get_resource_usage(self) -> SystemResourceUsage:
        """Sample and return the active CPU, RAM, and Disk space utilization values."""
        pass

    @abstractmethod
    def record_metric(self, metric: MetricSample) -> None:
        """Log a performance metric sample record into the telemetry registry."""
        pass

    @abstractmethod
    def get_metrics(self, metric_name: Optional[str] = None) -> List[MetricSample]:
        """Fetch historical performance metric samples, optionally filtered by metric name."""
        pass

    @abstractmethod
    def measure_latency(self, operation_name: str) -> Any:
        """Return a context manager context to time execution duration of a code block.
        
        Usage:
            with monitor.measure_latency("database_query"):
                # run DB code
        """
        pass
