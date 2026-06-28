"""
Developer Diagnostics Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List


@dataclass(frozen=True)
class DiagnosticsReport:
    """Immutable representation of the Developer Diagnostics report."""
    timestamp: datetime
    overall_status: str  # e.g., "HEALTHY", "DEGRADED", "UNHEALTHY"
    runtime_state: str
    config_status: Dict[str, Any]
    database_status: Dict[str, Any]
    health_summary: Dict[str, Any]
    performance_summary: Dict[str, Any]
    registered_services: List[str]
    event_bus_status: Dict[str, Any]
    policy_engine_status: Dict[str, Any]
    environment_information: Dict[str, Any]
    python_version: str
    platform_information: str
    extra_details: Dict[str, Any] = field(default_factory=dict)


class DiagnosticProvider(ABC):
    """Interface defining a subsystem that can expose custom diagnostics."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the subsystem or provider."""
        pass

    @abstractmethod
    def get_diagnostics(self) -> Dict[str, Any]:
        """Fetch custom diagnostic information from this subsystem."""
        pass


class DiagnosticsServicePort(ABC):
    """Interface for aggregating system diagnostics."""

    @abstractmethod
    def register_provider(self, provider: DiagnosticProvider) -> None:
        """Register a custom diagnostic provider."""
        pass

    @abstractmethod
    def get_diagnostics_report(self) -> DiagnosticsReport:
        """Generate and aggregate diagnostics from all sources."""
        pass
