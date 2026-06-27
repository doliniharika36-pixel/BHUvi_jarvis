"""
Health Monitor Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from typing import Callable, List
from jarvis_os.core.domain.entities import SubsystemStatus

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
