"""
Domain Entities for Jarvis OS.
These represent core business models and objects, completely implementation-agnostic.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

@dataclass
class ConfigEntry:
    """Represents a configuration key-value pair with schema info."""
    key: str
    value: Any
    value_type: str
    description: str
    is_sensitive: bool = False

@dataclass
class LogRecord:
    """Domain model representing a structured log entry."""
    timestamp: datetime
    level: str
    message: str
    module: str
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class SubsystemStatus:
    """Represents the health status of a Jarvis OS component."""
    name: str
    is_healthy: bool
    message: str
    last_checked: datetime
    details: Dict[str, Any] = field(default_factory=dict)

@dataclass
class MetricSample:
    """Represents a telemetry performance measurement point."""
    name: str
    value: float
    unit: str
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class LLMMessage:
    """A single message within an LLM chat payload."""
    role: str  # 'system', 'user', 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class LLMResponse:
    """Result of an LLM generation call, containing metadata."""
    content: str
    token_usage: Dict[str, int] = field(default_factory=dict)
    model_name: str = ""
    elapsed_seconds: float = 0.0
