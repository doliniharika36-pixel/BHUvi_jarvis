"""
Jarvis OS Tool Framework Exceptions
"""

class ToolException(Exception):
    """Base exception for all tool-related errors in Jarvis OS."""
    pass


class ToolNotFoundException(ToolException):
    """Raised when a requested tool cannot be found in the registry."""
    pass


class DuplicateToolException(ToolException):
    """Raised when a tool with the same name is already registered."""
    pass


class ToolExecutionException(ToolException):
    """Raised when a tool execution fails."""
    pass
