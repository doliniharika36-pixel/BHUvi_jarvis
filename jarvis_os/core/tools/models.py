"""
Jarvis OS Tool Framework Models
"""
from typing import Dict, Any, Optional

class ToolContext:
    """Represents the execution context shared with the tool."""
    def __init__(self, variables: Optional[Dict[str, Any]] = None):
        self.variables = variables if variables is not None else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self.variables.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self.variables[key] = value


class ToolMetadata:
    """Metadata detailing the tool properties."""
    def __init__(self, name: str, description: str, version: str = "1.0.0", enabled: bool = True):
        self.name = name
        self.description = description
        self.version = version
        self.enabled = enabled


class ToolRequest:
    """Encapsulates a request to execute a tool with specific arguments and context."""
    def __init__(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None, context: Optional[ToolContext] = None):
        self.tool_name = tool_name
        self.arguments = arguments if arguments is not None else {}
        self.context = context if context is not None else ToolContext()


class ToolResult:
    """Contains the output or error information resulting from a tool execution."""
    def __init__(self, success: bool, output: Any = None, error_message: Optional[str] = None):
        self.success = success
        self.output = output
        self.error_message = error_message
