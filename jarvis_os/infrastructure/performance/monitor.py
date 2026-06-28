"""
Concrete PerformanceMonitor and resource samplers for Jarvis OS.

Implements the PerformanceMonitorPort contract, offering thread-safe metric logging,
latency measurement context managers, and provider-based telemetry aggregation.
Uses pure ctypes for standard library resource metrics sampling on Windows.
"""
import contextlib
import ctypes
from datetime import datetime
import os
import sys
import threading
from typing import Any, Dict, Generator, List, Optional

from jarvis_os.core.ports.performance import (
    PerformanceMonitorPort,
    PerformanceProvider,
    PerformanceSnapshot,
)
from jarvis_os.core.domain.value_objects import SystemResourceUsage
from jarvis_os.core.domain.entities import MetricSample


# ═══════════════════════════════════════════════════════════════════════ #
#  Windows Ctypes Structures                                              #
# ═══════════════════════════════════════════════════════════════════════ #

if sys.platform == "win32":
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    class FILETIME(ctypes.Structure):
        _fields_ = [
            ("dwLowDateTime", ctypes.c_ulong),
            ("dwHighDateTime", ctypes.c_ulong),
        ]


# ═══════════════════════════════════════════════════════════════════════ #
#  System Resource Sampler                                                #
# ═══════════════════════════════════════════════════════════════════════ #

class SystemResourceSampler:
    """Samples CPU and RAM metrics using pure stdlib standard system APIs."""

    def __init__(self) -> None:
        self._last_sys_cpu = 0.0
        self._last_process_cpu = 0.0
        self._last_sample_time = time_func = getattr(sys, "platform", "")
        self._cpu_lock = threading.Lock()

        # Initialize base ticks for CPU calculation
        self._prev_idle_ticks = 0
        self._prev_kernel_ticks = 0
        self._prev_user_ticks = 0
        self._initialize_cpu_ticks()

    def _initialize_cpu_ticks(self) -> None:
        if sys.platform == "win32":
            try:
                idle = FILETIME()
                kernel = FILETIME()
                user = FILETIME()
                if ctypes.windll.kernel32.GetSystemTimes(
                    ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
                ):
                    self._prev_idle_ticks = (idle.dwHighDateTime << 32) + idle.dwLowDateTime
                    self._prev_kernel_ticks = (kernel.dwHighDateTime << 32) + kernel.dwLowDateTime
                    self._prev_user_ticks = (user.dwHighDateTime << 32) + user.dwLowDateTime
            except Exception:
                pass

    def sample_usage(self) -> SystemResourceUsage:
        """Sample active CPU, RAM, and Disk space utilization values."""
        # 1. Disk usage (Pure standard library shutil)
        import shutil
        try:
            total_disk, used_disk, free_disk = shutil.disk_usage(".")
        except Exception:
            total_disk, used_disk, free_disk = 1, 0, 1

        # 2. Memory usage
        ram_used = 0
        ram_total = 1024 * 1024 * 1024  # 1 GB default fallback
        if sys.platform == "win32":
            try:
                stat = MEMORYSTATUSEX()
                stat.dwLength = ctypes.sizeof(stat)
                if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
                    ram_total = stat.ullTotalPhys
                    ram_used = stat.ullTotalPhys - stat.ullAvailPhys
            except Exception:
                pass
        else:
            # POSIX fallback
            try:
                import resource
                # rusage maxrss is in KB on Linux/macOS
                ram_used = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
            except Exception:
                pass

        # 3. CPU usage calculation
        cpu_percent = 0.0
        if sys.platform == "win32":
            with self._cpu_lock:
                try:
                    idle = FILETIME()
                    kernel = FILETIME()
                    user = FILETIME()
                    if ctypes.windll.kernel32.GetSystemTimes(
                        ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)
                    ):
                        curr_idle = (idle.dwHighDateTime << 32) + idle.dwLowDateTime
                        curr_kernel = (kernel.dwHighDateTime << 32) + kernel.dwLowDateTime
                        curr_user = (user.dwHighDateTime << 32) + user.dwLowDateTime

                        idle_diff = curr_idle - self._prev_idle_ticks
                        kernel_diff = curr_kernel - self._prev_kernel_ticks
                        user_diff = curr_user - self._prev_user_ticks

                        total_sys = kernel_diff + user_diff
                        if total_sys > 0:
                            # Kernel ticks include idle time ticks on Windows; subtract idle
                            active_sys = total_sys - idle_diff
                            cpu_percent = (active_sys / total_sys) * 100.0
                            # Bound
                            cpu_percent = max(0.0, min(100.0, cpu_percent))

                        self._prev_idle_ticks = curr_idle
                        self._prev_kernel_ticks = curr_kernel
                        self._prev_user_ticks = curr_user
                except Exception:
                    pass
        else:
            # POSIX fallback using load average
            try:
                cpu_percent = os.getloadavg()[0] * 10.0  # normalize load average roughly
            except Exception:
                pass

        return SystemResourceUsage(
            cpu_percent=cpu_percent,
            ram_used_bytes=ram_used,
            ram_total_bytes=ram_total,
            disk_used_bytes=used_disk,
            disk_free_bytes=free_disk,
        )


# ═══════════════════════════════════════════════════════════════════════ #
#  Performance Monitor                                                     #
# ═══════════════════════════════════════════════════════════════════════ #

class PerformanceMonitor(PerformanceMonitorPort):
    """Thread-safe performance monitoring and latency measurement tool."""

    def __init__(self, sampler: Optional[SystemResourceSampler] = None) -> None:
        self._sampler = sampler or SystemResourceSampler()
        self._metrics: List[MetricSample] = []
        self._providers: Dict[str, PerformanceProvider] = {}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # PerformanceMonitorPort Implementation                                #
    # ------------------------------------------------------------------ #

    def get_resource_usage(self) -> SystemResourceUsage:
        """Sample active CPU and RAM resource values."""
        return self._sampler.sample_usage()

    def record_metric(self, metric: MetricSample) -> None:
        """Add a performance metric sample to the in-memory registry."""
        with self._lock:
            self._metrics.append(metric)

    def get_metrics(self, metric_name: Optional[str] = None) -> List[MetricSample]:
        """Retrieve recorded metrics, optionally filtered by name."""
        with self._lock:
            if metric_name:
                return [m for m in self._metrics if m.name == metric_name]
            return list(self._metrics)

    @contextlib.contextmanager
    def measure_latency(self, operation_name: str) -> Generator[None, None, None]:
        """Context manager to measure the latency duration of a code block."""
        start_time = datetime.now()
        yield
        elapsed = (datetime.now() - start_time).total_seconds()
        self.record_metric(
            MetricSample(
                name=f"{operation_name}_latency",
                value=elapsed,
                unit="seconds",
                timestamp=datetime.now(),
            )
        )

    def register_provider(self, provider: PerformanceProvider) -> None:
        """Register a subsystem metric provider."""
        with self._lock:
            self._providers[provider.name] = provider

    def get_performance_snapshot(self) -> PerformanceSnapshot:
        """Query all providers, merge metrics, and return a PerformanceSnapshot."""
        with self._lock:
            providers = list(self._providers.values())
            # Copy internal metrics to the snapshot
            merged_metrics = list(self._metrics)

        for provider in providers:
            try:
                # Safe evaluation: failures in one provider must not stop others
                sub_metrics = provider.get_metrics()
                merged_metrics.extend(sub_metrics)
            except Exception as exc:
                # Safe fallback: log/record the error as a metric but don't crash
                merged_metrics.append(
                    MetricSample(
                        name=f"{provider.name}_provider_failure",
                        value=1.0,
                        unit="count",
                        timestamp=datetime.now(),
                        metadata={"error": str(exc)},
                    )
                )

        return PerformanceSnapshot(
            timestamp=datetime.now(),
            metrics=merged_metrics,
        )

    # ------------------------------------------------------------------ #
    # Helper for testing                                                   #
    # ------------------------------------------------------------------ #

    def clear(self) -> None:
        """Reset internal metrics list."""
        with self._lock:
            self._metrics.clear()
            self._providers.clear()
