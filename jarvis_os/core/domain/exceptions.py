"""
Domain Exception Contracts for Jarvis OS.
All system components must raise or subclass these errors to maintain implementation-agnostic behavior.
"""

class JarvisException(Exception):
    """Base exception for all Jarvis OS errors."""
    pass

class DIResolutionError(JarvisException):
    """Raised when a dependency resolution fails in the DI container."""
    pass


class ConfigurationError(JarvisException):
    """Raised when there is an issue loading or validating configuration."""
    pass

class SecurityException(JarvisException):
    """Base error for security violations."""
    pass

class UnauthorizedError(SecurityException):
    """Raised when a policy check fails for an action."""
    pass

class PathValidationError(SecurityException):
    """Raised when a path traversal or invalid path is detected."""
    pass

class CommandValidationError(SecurityException):
    """Raised when a system command violates validation rules."""
    pass

class RepositoryException(JarvisException):
    """Raised when a repository operation (database, vector search) fails."""
    pass

class LLMException(JarvisException):
    """Raised when the LLM service fails or returns an invalid response."""
    pass

class EventBusException(JarvisException):
    """Raised when event publishing or subscription fails."""
    pass

class SubsystemError(JarvisException):
    """Raised when a downstream port or service fails (e.g., STT, TTS)."""
    pass

class PerformanceThresholdExceeded(JarvisException):
    """Raised when a telemetry or resource usage limit is breached."""
    pass
