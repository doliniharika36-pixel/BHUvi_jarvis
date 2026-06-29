"""
Jarvis OS Tool Abstract Base Class
"""
from abc import ABC, abstractmethod
from jarvis_os.core.tools.models import ToolContext, ToolResult

class Tool(ABC):
    """Abstract base class for all tools executed by Jarvis OS."""

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
    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        """
        Execute the tool action with the provided context and keyword arguments.
        
        Args:
            context: The ToolContext containing shared variables.
            **kwargs: Arguments required by the tool.
            
        Returns:
            A ToolResult object containing execution status and outputs.
        """
        pass
