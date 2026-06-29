"""
Jarvis OS Desktop Automation Framework Exceptions
"""

class AutomationException(Exception):
    """Base exception for all desktop automation errors in Jarvis OS."""
    pass


class AutomationNotFoundException(AutomationException):
    """Raised when a requested automation action is not found in the registry."""
    pass


class DuplicateAutomationException(AutomationException):
    """Raised when an automation action is already registered under the same name."""
    pass


class AutomationExecutionException(AutomationException):
    """Raised when execution of an automation action fails."""
    pass
