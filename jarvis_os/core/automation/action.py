"""
Jarvis OS Desktop Automation Action Base Class
"""
from abc import ABC, abstractmethod
from jarvis_os.core.automation.models import AutomationContext, AutomationResult

class AutomationAction(ABC):
    """Abstract base class representing an automatable unit of work on the desktop."""

    def __init__(self, name: str, description: str, version: str = "1.0.0", enabled: bool = True):
        self._name = name
        self._description = description
        self._version = version
        self.enabled = enabled

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def version(self) -> str:
        return self._version

    @abstractmethod
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        """
        Executes the automation logic.
        
        Args:
            context: Shared system/automation context.
            **kwargs: Configurable parameters for the action.
            
        Returns:
            An AutomationResult describing success, outputs, or failures.
        """
        pass
