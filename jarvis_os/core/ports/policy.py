"""
Policy Port Contract for Jarvis OS.
"""
from abc import ABC, abstractmethod
from jarvis_os.core.domain.value_objects import UserIdentity

class PolicyPort(ABC):
    """Interface defining system security policies and safety guardrail checks."""

    @abstractmethod
    def is_authorized(self, user: UserIdentity, action: str, resource: str) -> bool:
        """Check if a given user identity is authorized to execute an action on a resource."""
        pass

    @abstractmethod
    def validate_command(self, command_line: str) -> bool:
        """Validate a shell command string against safety rules to prevent injection.
        
        Raises:
            CommandValidationError: If validation fails.
        """
        pass

    @abstractmethod
    def validate_path(self, target_path: str) -> bool:
        """Validate a filesystem path target to ensure it doesn't escape allowed folders.
        
        Raises:
            PathValidationError: If the path is outside the sandbox limits.
        """
        pass
