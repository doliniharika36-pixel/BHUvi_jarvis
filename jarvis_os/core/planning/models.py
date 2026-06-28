from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple


class ExecutionStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class ExecutionStep:
    id: str
    description: str
    action: str
    dependencies: Tuple[str, ...] = field(default_factory=tuple)
    retry_limit: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlan:
    id: str
    goal: str
    steps: Tuple[ExecutionStep, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
