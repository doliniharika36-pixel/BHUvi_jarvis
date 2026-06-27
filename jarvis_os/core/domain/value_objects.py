"""
Domain Value Objects for Jarvis OS.
These represent immutable concepts defined entirely by their attributes.
"""
from dataclasses import dataclass, field
from typing import List, Pattern

@dataclass(frozen=True)
class SystemResourceUsage:
    """Represents CPU, RAM, and disk utilization metrics."""
    cpu_percent: float
    ram_used_bytes: int
    ram_total_bytes: int
    disk_used_bytes: int
    disk_free_bytes: int

@dataclass(frozen=True)
class PathPermission:
    """Defines permission rules for a directory or file path."""
    allowed_root_path: str
    can_read: bool
    can_write: bool

@dataclass(frozen=True)
class CommandDefinition:
    """Defines structural criteria for verifying shell commands."""
    executable: str
    allowed_arguments_patterns: List[str] = field(default_factory=list)
    requires_user_confirmation: bool = True

@dataclass(frozen=True)
class UserIdentity:
    """Represents a client identity for permission validation."""
    identity_id: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
