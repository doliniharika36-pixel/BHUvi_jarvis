"""
Concrete Developer Diagnostics Service implementation for Jarvis OS.
"""
import os
import platform
import sys
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from jarvis_os.core.ports.diagnostics import (
    DiagnosticsServicePort,
    DiagnosticProvider,
    DiagnosticsReport,
)
from jarvis_os.core.ports.config import ConfigurationPort
from jarvis_os.core.ports.runtime import RuntimePort
from jarvis_os.core.ports.event_bus import EventBusPort
from jarvis_os.core.ports.policy import PolicyPort
from jarvis_os.core.ports.health import HealthMonitorPort
from jarvis_os.core.ports.performance import PerformanceMonitorPort


class DiagnosticsService(DiagnosticsServicePort):
    """Aggregates platform diagnostics from all system components thread-safely and read-only."""

    def __init__(
        self,
        config: Optional[ConfigurationPort] = None,
        runtime: Optional[RuntimePort] = None,
        db_manager: Optional[Any] = None,
        event_bus: Optional[EventBusPort] = None,
        policy_engine: Optional[PolicyPort] = None,
        health_monitor: Optional[HealthMonitorPort] = None,
        performance_monitor: Optional[PerformanceMonitorPort] = None,
    ) -> None:
        self._config = config
        self._runtime = runtime
        self._db_manager = db_manager
        self._event_bus = event_bus
        self._policy_engine = policy_engine
        self._health_monitor = health_monitor
        self._performance_monitor = performance_monitor

        self._custom_providers: Dict[str, DiagnosticProvider] = {}
        self._lock = threading.RLock()

    def register_provider(self, provider: DiagnosticProvider) -> None:
        """Register a custom diagnostic provider."""
        with self._lock:
            self._custom_providers[provider.name] = provider

    def get_diagnostics_report(self) -> DiagnosticsReport:
        """Generate and aggregate diagnostics from all sources.
        
        This operation is strictly read-only and has no side effects.
        """
        # 1. Fetch current timestamp
        timestamp = datetime.now()

        # 2. Get environment information
        python_version = sys.version
        platform_info = f"{platform.system()} {platform.release()} ({platform.machine()})"
        env_info = {
            "os_name": platform.system(),
            "os_release": platform.release(),
            "architecture": platform.machine(),
            "python_implementation": platform.python_implementation(),
            "process_id": os.getpid(),
        }

        # 3. Jarvis version from config
        jarvis_version = "1.0.0"
        if self._config:
            try:
                jarvis_version = self._config.get("jarvis.version", "1.0.0")
            except Exception:
                pass

        # 4. Configuration Status
        config_status: Dict[str, Any] = {}
        if self._config:
            try:
                # Read-only validation call
                is_valid = self._config.validate()
                config_status["valid"] = bool(is_valid)
            except Exception as exc:
                config_status["valid"] = False
                config_status["error"] = str(exc)
        else:
            config_status["valid"] = False
            config_status["error"] = "Configuration service is not registered."

        # 5. Runtime Lifecycle Status & Services
        runtime_state = "UNKNOWN"
        registered_services: List[str] = []
        if self._runtime:
            try:
                # Safely inspect state if ApplicationHost or custom lifecycle
                lifecycle = getattr(self._runtime, "lifecycle", None)
                if lifecycle and hasattr(lifecycle, "state"):
                    state_val = lifecycle.state
                    runtime_state = getattr(state_val, "name", str(state_val))
                else:
                    runtime_state = "RUNNING" if self._runtime.is_running() else "STOPPED"
            except Exception as exc:
                runtime_state = f"ERROR: {exc}"

            try:
                # List services from ServiceRegistry if available
                registry = getattr(self._runtime, "registry", None)
                if registry and hasattr(registry, "list_services"):
                    registered_services = list(registry.list_services())
                elif hasattr(self._runtime, "list_services"):
                    registered_services = list(self._runtime.list_services())
            except Exception:
                pass
        else:
            runtime_state = "MISSING"

        # 6. Database Connectivity Check
        database_status: Dict[str, Any] = {}
        if self._db_manager:
            try:
                is_open = bool(getattr(self._db_manager, "is_open", False))
                database_status["open"] = is_open
                database_status["path"] = getattr(self._db_manager, "_db_path", "unknown")
                if is_open:
                    # Run a read-only schema version query to verify active connection
                    res = self._db_manager.fetch_one("PRAGMA schema_version")
                    if res is not None:
                        database_status["connected"] = True
                        database_status["schema_version"] = res[0]
                    else:
                        database_status["connected"] = True
                else:
                    database_status["connected"] = False
                    database_status["error"] = "Database connection is closed."
            except Exception as exc:
                database_status["connected"] = False
                database_status["error"] = str(exc)
        else:
            database_status["connected"] = False
            database_status["open"] = False
            database_status["error"] = "Database manager is not registered."

        # 7. Event Bus Status
        event_bus_status: Dict[str, Any] = {}
        if self._event_bus:
            event_bus_status["available"] = True
            try:
                # Count subscribers and handlers safely
                subscribers = getattr(self._event_bus, "_subscribers", {})
                event_bus_status["subscriber_types_count"] = len(subscribers)
                total_handlers = sum(len(handlers) for handlers in subscribers.values())
                event_bus_status["total_handlers_count"] = total_handlers
            except Exception as exc:
                event_bus_status["inspection_error"] = str(exc)
        else:
            event_bus_status["available"] = False
            event_bus_status["error"] = "Event Bus is not registered."

        # 8. Policy Engine Status
        policy_engine_status: Dict[str, Any] = {}
        if self._policy_engine:
            policy_engine_status["available"] = True
            try:
                rules = getattr(self._policy_engine, "_rules", [])
                paths = getattr(self._policy_engine, "_path_permissions", [])
                commands = getattr(self._policy_engine, "_command_definitions", [])
                policy_engine_status["rule_count"] = len(rules)
                policy_engine_status["path_permission_count"] = len(paths)
                policy_engine_status["command_definition_count"] = len(commands)
            except Exception as exc:
                policy_engine_status["inspection_error"] = str(exc)
        else:
            policy_engine_status["available"] = False
            policy_engine_status["error"] = "Policy Engine is not registered."

        # 9. Health Summary Integration (Milestone 5A)
        health_summary: Dict[str, Any] = {}
        health_report_status = "UNKNOWN"
        if self._health_monitor:
            try:
                # Fetch full health report
                report = self._health_monitor.get_health_report(timeout=2.0)
                health_report_status = getattr(report.overall_status, "name", str(report.overall_status))
                health_summary["status"] = health_report_status
                health_summary["checked_at"] = report.checked_at.isoformat()
                health_summary["subsystems"] = [
                    {
                        "name": sub.name,
                        "status": getattr(sub.status, "name", str(sub.status)),
                        "message": sub.message,
                    }
                    for sub in report.subsystems
                ]
            except Exception as exc:
                health_summary["status"] = "ERROR"
                health_summary["error"] = str(exc)
                health_report_status = "UNHEALTHY"
        else:
            health_summary["status"] = "UNKNOWN"
            health_summary["error"] = "Health Monitor is not registered."

        # 10. Performance Summary Integration (Milestone 5B)
        performance_summary: Dict[str, Any] = {}
        if self._performance_monitor:
            try:
                # Use public PerformanceMonitorPort resource usage contract
                usage = self._performance_monitor.get_resource_usage()
                performance_summary["cpu_percent"] = usage.cpu_percent
                performance_summary["ram_used_bytes"] = usage.ram_used_bytes
                performance_summary["ram_total_bytes"] = usage.ram_total_bytes
                performance_summary["disk_used_bytes"] = usage.disk_used_bytes
                performance_summary["disk_free_bytes"] = usage.disk_free_bytes
            except Exception as exc:
                performance_summary["resource_usage_error"] = str(exc)

            try:
                # Use public PerformanceMonitorPort get_metrics contract
                metrics = self._performance_monitor.get_metrics()
                performance_summary["metric_count"] = len(metrics)
            except Exception as exc:
                performance_summary["metrics_error"] = str(exc)

            # Concrete aggregator fallback (if present)
            if hasattr(self._performance_monitor, "get_performance_snapshot"):
                try:
                    snapshot = self._performance_monitor.get_performance_snapshot()
                    performance_summary["snapshot_metrics_count"] = len(snapshot.metrics)
                except Exception as exc:
                    performance_summary["snapshot_error"] = str(exc)
        else:
            performance_summary["error"] = "Performance Monitor is not registered."

        # 11. Custom Diagnostic Providers
        extra_details: Dict[str, Any] = {}
        with self._lock:
            custom_providers = list(self._custom_providers.values())

        for prov in custom_providers:
            try:
                extra_details[prov.name] = prov.get_diagnostics()
            except Exception as exc:
                extra_details[prov.name] = {"error": f"Diagnostics collection failed: {exc}"}

        # Determine overall status
        overall_status = "HEALTHY"
        if not config_status.get("valid", False) or not database_status.get("connected", False) or health_report_status == "UNHEALTHY":
            overall_status = "UNHEALTHY"
        elif health_report_status == "DEGRADED":
            overall_status = "DEGRADED"

        return DiagnosticsReport(
            timestamp=timestamp,
            overall_status=overall_status,
            runtime_state=runtime_state,
            config_status=config_status,
            database_status=database_status,
            health_summary=health_summary,
            performance_summary=performance_summary,
            registered_services=registered_services,
            event_bus_status=event_bus_status,
            policy_engine_status=policy_engine_status,
            environment_information=env_info,
            python_version=python_version,
            platform_information=platform_info,
            extra_details=extra_details,
        )

    @staticmethod
    def format_report_to_human_readable(report: DiagnosticsReport) -> str:
        """Convert a DiagnosticsReport into a clean, human-readable CLI-friendly text report."""
        lines = [
            "======================================================================",
            "                       DEVELOPER DIAGNOSTICS REPORT                   ",
            "======================================================================",
            f"Timestamp:             {report.timestamp.isoformat()}",
            f"Overall Status:        {report.overall_status}",
            f"Runtime State:         {report.runtime_state}",
            f"Python Version:        {report.python_version.splitlines()[0]}",
            f"Platform:              {report.platform_information}",
            "----------------------------------------------------------------------",
            "Configuration Status:",
            f"  Valid:               {report.config_status.get('valid')}",
        ]
        if "error" in report.config_status:
            lines.append(f"  Error:               {report.config_status['error']}")

        lines.extend([
            "----------------------------------------------------------------------",
            "Database Connectivity:",
            f"  Open:                {report.database_status.get('open')}",
            f"  Connected:           {report.database_status.get('connected')}",
            f"  Path:                {report.database_status.get('path')}",
        ])
        if "schema_version" in report.database_status:
            lines.append(f"  Schema Version:      {report.database_status['schema_version']}")
        if "error" in report.database_status:
            lines.append(f"  Error:               {report.database_status['error']}")

        lines.extend([
            "----------------------------------------------------------------------",
            "Subsystems Health Summary:",
            f"  Overall Status:      {report.health_summary.get('status')}",
        ])
        for sub in report.health_summary.get("subsystems", []):
            lines.append(f"  - [{sub['name']}] Status: {sub['status']} | Message: {sub['message']}")
        if "error" in report.health_summary:
            lines.append(f"  Error:               {report.health_summary['error']}")

        lines.extend([
            "----------------------------------------------------------------------",
            "Performance Telemetry Summary:",
        ])
        perf = report.performance_summary
        if "error" in perf:
            lines.append(f"  Error:               {perf['error']}")
        else:
            if "cpu_percent" in perf:
                lines.append(f"  CPU Utilization:     {perf['cpu_percent']:.1f}%")
            if "ram_used_bytes" in perf and "ram_total_bytes" in perf:
                used_mb = perf["ram_used_bytes"] / (1024 * 1024)
                total_mb = perf["ram_total_bytes"] / (1024 * 1024)
                lines.append(f"  RAM Usage:           {used_mb:.1f} MB / {total_mb:.1f} MB")
            if "disk_used_bytes" in perf and "disk_free_bytes" in perf:
                used_gb = perf["disk_used_bytes"] / (1024 * 1024 * 1024)
                free_gb = perf["disk_free_bytes"] / (1024 * 1024 * 1024)
                lines.append(f"  Disk Space:          {used_gb:.1f} GB Used / {free_gb:.1f} GB Free")
            lines.append(f"  In-Memory Metrics:   {perf.get('metric_count', 0)} samples")

        lines.extend([
            "----------------------------------------------------------------------",
            "Platform Component Metrics:",
            f"  Registered Services: {', '.join(report.registered_services) if report.registered_services else 'None'}",
        ])

        eb = report.event_bus_status
        if eb.get("available"):
            lines.append(f"  Event Bus:           {eb.get('subscriber_types_count', 0)} event types | {eb.get('total_handlers_count', 0)} handlers")
        else:
            lines.append(f"  Event Bus:           Offline ({eb.get('error')})")

        pol = report.policy_engine_status
        if pol.get("available"):
            lines.append(f"  Policy Engine:       {pol.get('rule_count', 0)} rules | {pol.get('path_permission_count', 0)} path policies | {pol.get('command_definition_count', 0)} command specs")
        else:
            lines.append(f"  Policy Engine:       Offline ({pol.get('error')})")

        if report.extra_details:
            lines.extend([
                "----------------------------------------------------------------------",
                "Custom Diagnostic Providers:",
            ])
            for name, details in report.extra_details.items():
                lines.append(f"  - [{name}]: {details}")

        lines.append("======================================================================")
        return "\n".join(lines)
