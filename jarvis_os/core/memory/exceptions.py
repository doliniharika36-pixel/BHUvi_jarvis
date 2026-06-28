from jarvis_os.core.domain.exceptions import JarvisException


class MemoryError(JarvisException):
    """Base exception for memory subsystem failures."""
    pass


class MemoryNotFoundError(MemoryError):
    """Raised when an operation targets a nonexistent memory record."""
    pass


class MemoryValidationError(MemoryError):
    """Raised when memory input fails validation."""
    pass
