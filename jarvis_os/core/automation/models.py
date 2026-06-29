"""
Jarvis OS Desktop Automation Framework Models
"""
from typing import Dict, Any, Optional

class AutomationContext:
    """Represents the environmental or session context supplied during automation execution."""
    def __init__(self, variables: Optional[Dict[str, Any]] = None):
        self.variables = variables if variables is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value


class AutomationMetadata:
    """Contains information detailing registered automation actions."""
    def __init__(self, name: str, description: str, version: str = "1.0.0", enabled: bool = True):
        self.name = name
        self.description = description
        self.version = version
        self.enabled = enabled


class AutomationRequest:
    """Encapsulates a request to execute a specific automation action."""
    def __init__(self, action_name: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[AutomationContext] = None):
        self.action_name = action_name
        self.parameters = parameters if parameters is not None else {}
        self.context = context if context is not None else AutomationContext()


class AutomationResult:
    """Represents the outcome of executing an automation action."""
    def __init__(self, success: bool, output: Any = None, error_message: Optional[str] = None):
        self.success = success
        self.output = output
        self.error_message = error_message
