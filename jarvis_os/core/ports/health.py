"""
Health Monitor Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from jarvis_os.core.domain.entities import SubsystemStatus


class HealthStatus(Enum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"


@dataclass(frozen=True)
class SubsystemHealth:
    """Represents the rich health state of a single subsystem."""
    name: str
    status: HealthStatus
    message: str
    last_checked: datetime
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class HealthReport:
    """Aggregated health state of all subsystems in the platform."""
    overall_status: HealthStatus
    checked_at: datetime
    subsystems: List[SubsystemHealth] = field(default_factory=list)


class HealthProvider(ABC):
    """Interface defining a subsystem that can execute its own health checks."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Name of the subsystem."""
        pass

    @abstractmethod
    def get_health(self) -> SubsystemHealth:
        """Run self-checks and return the current health state."""
        pass


class HealthMonitorPort(ABC):
    """Interface defining system and subsystem health tracking capabilities."""

    @abstractmethod
    def check_health(self) -> List[SubsystemStatus]:
        """Query and return the health status list of all registered subsystems."""
        pass

    @abstractmethod
    def check_subsystem(self, name: str) -> SubsystemStatus:
        """Query the health state of a specific subsystem by name.

        Raises:
            SubsystemError: If the subsystem is not registered.
        """
        pass

    @abstractmethod
    def register_subsystem(self, name: str, checker: Callable[[], SubsystemStatus]) -> None:
        """Register a health checking function for a system component."""
        pass

    @abstractmethod
    def get_health_report(self, timeout: float = 2.0) -> HealthReport:
        """Aggregate health from all registered HealthProviders into a HealthReport.

        Args:
            timeout: Max seconds allowed for each provider's health check.
        """
        pass

    @abstractmethod
    def register_provider(self, provider: HealthProvider) -> None:
        """Register a HealthProvider implementation to be aggregated."""
        pass
