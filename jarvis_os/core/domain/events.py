"""
Domain Events for Jarvis OS.
These define the core events that decouple system components.
"""
from dataclasses import dataclass, field
from datetime import datetime
import uuid
from typing import Any, Dict

@dataclass
class DomainEvent:
    """Base domain event class."""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class SystemBootstrappedEvent(DomainEvent):
    """Emitted when the Jarvis OS runtime completes initialization."""
    runtime_version: str = "1.0"
    startup_time_ms: float = 0.0

@dataclass
class SystemShutdownEvent(DomainEvent):
    """Emitted when the Jarvis OS runtime begins shutdown."""
    reason: str = "user_request"

@dataclass
class ConfigurationChangedEvent(DomainEvent):
    """Emitted when a configuration key value is updated."""
    key: str = ""
    old_value: Any = None
    new_value: Any = None

@dataclass
class SubsystemHealthChangedEvent(DomainEvent):
    """Emitted when a subsystem changes health status."""
    subsystem_name: str = ""
    is_healthy: bool = False
    message: str = ""

@dataclass
class SecurityViolationEvent(DomainEvent):
    """Emitted when a security block or validation failure occurs."""
    violation_type: str = ""  # e.g., 'unauthorized_action', 'path_traversal', 'command_injection'
    subject: str = ""
    resource: str = ""
    details: str = ""

@dataclass
class PerformanceAlertEvent(DomainEvent):
    """Emitted when resource usage exceeds system limits."""
    metric_name: str = ""
    threshold: float = 0.0
    actual_value: float = 0.0
    message: str = ""

@dataclass
class LLMQueryExecutedEvent(DomainEvent):
    """Emitted when an LLM call is completed."""
    prompt_length: int = 0
    response_length: int = 0
    elapsed_seconds: float = 0.0
    model_name: str = ""
