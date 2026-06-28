from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Tuple

from jarvis_os.core.planning.models import ExecutionStep


class PlanStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


@dataclass(frozen=True)
class StepExecutionState:
    step_id: str
    status: str
    attempts: int = 0
    last_error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecutionPlanState:
    plan_id: str
    status: PlanStatus
    progress: float
    step_states: Tuple[StepExecutionState, ...]
    metadata: Dict[str, Any] = field(default_factory=dict)
