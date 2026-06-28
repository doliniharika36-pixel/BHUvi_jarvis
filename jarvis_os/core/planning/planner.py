from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

from jarvis_os.core.planning.models import ExecutionPlan, ExecutionStep


@dataclass(frozen=True)
class PlanningRequest:
    goal: str
    tool_candidates: Tuple[str, ...] = ()


class Planner:
    """Deterministic planner converting a goal into an execution plan."""

    def plan(self, request: PlanningRequest) -> ExecutionPlan:
        if not request.goal or not request.goal.strip():
            raise ValueError("goal must be a non-empty string")

        steps = self._derive_steps(request.goal, request.tool_candidates)
        plan_id = request.goal.strip().replace(" ", "_").lower()[:64]
        return ExecutionPlan(id=plan_id, goal=request.goal.strip(), steps=tuple(steps))

    def _derive_steps(self, goal: str, tool_candidates: Iterable[str]) -> List[ExecutionStep]:
        normalized = goal.strip().lower()
        steps: List[ExecutionStep] = []

        if "open" in normalized and "chrome" in normalized:
            steps.append(ExecutionStep(id="step_open_chrome", description="Open Chrome browser", action="open_chrome"))
        if "screenshot" in normalized:
            steps.append(ExecutionStep(id="step_screenshot", description="Take screenshot", action="screenshot", dependencies=("step_open_chrome",) if any(s.startswith("open_chrome") for s in tool_candidates) else ()))
        if not steps:
            steps.append(ExecutionStep(id="step_analyze_goal", description="Analyze goal and prepare execution", action="noop"))

        return steps
