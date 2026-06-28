from __future__ import annotations

import threading
from typing import Callable, Dict, List, Tuple

from jarvis_os.core.execution.models import ExecutionPlanState, PlanStatus, StepExecutionState
from jarvis_os.core.planning.models import ExecutionPlan, ExecutionStep


class ExecutorError(Exception):
    pass


class Executor:
    """Executes execution plans sequentially with support for retries and cancellation."""

    def __init__(self, action_registry: Dict[str, Callable[[ExecutionStep], bool]]) -> None:
        self._action_registry = action_registry
        self._lock = threading.RLock()

    def execute(self, plan: ExecutionPlan) -> ExecutionPlanState:
        if not plan.steps:
            raise ValueError("ExecutionPlan must contain at least one step")

        with self._lock:
            state = self._initialize_state(plan)
            state = self._set_status(state, PlanStatus.RUNNING)

            for step in plan.steps:
                if state.status in {PlanStatus.FAILED, PlanStatus.CANCELED}:
                    break

                if not self._dependencies_satisfied(step, state):
                    state = self._mark_failed(state, step.id, "unsatisfied dependencies")
                    break

                state = self._mark_step_running(state, step.id)
                success, state = self._run_step(step, state)
                if not success:
                    if self._should_retry(step, state):
                        success, state = self._retry_step(step, state)
                    if not success:
                        step_state = self._get_step_state(state, step.id)
                        if not step_state.last_error:
                            state = self._mark_failed(state, step.id, "step failed")
                        else:
                            state = self._set_status(state, PlanStatus.FAILED)
                        break
                state = self._mark_completed(state, step.id)

            if state.status == PlanStatus.RUNNING:
                state = self._set_status(state, PlanStatus.COMPLETED)
            return state

    def cancel(self, state: ExecutionPlanState, reason: str = "canceled") -> ExecutionPlanState:
        return self._mark_canceled(state, reason)

    def _initialize_state(self, plan: ExecutionPlan) -> ExecutionPlanState:
        return ExecutionPlanState(
            plan_id=plan.id,
            status=PlanStatus.PENDING,
            progress=0.0,
            step_states=tuple(
                StepExecutionState(step_id=step.id, status=PlanStatus.PENDING.value)
                for step in plan.steps
            ),
        )

    def _dependencies_satisfied(self, step: ExecutionStep, state: ExecutionPlanState) -> bool:
        completed_steps = {s.step_id for s in state.step_states if s.status == PlanStatus.COMPLETED.value}
        return all(dep in completed_steps for dep in step.dependencies)

    def _run_step(self, step: ExecutionStep, state: ExecutionPlanState) -> Tuple[bool, ExecutionPlanState]:
        action = self._action_registry.get(step.action)
        if action is None:
            return False, self._mark_failed(state, step.id, f"unknown action '{step.action}'")

        try:
            success = action(step)
            return bool(success), state
        except Exception as exc:
            return False, self._mark_failed(state, step.id, str(exc))

    def _should_retry(self, step: ExecutionStep, state: ExecutionPlanState) -> bool:
        step_state = self._get_step_state(state, step.id)
        return step_state.attempts < step.retry_limit

    def _retry_step(self, step: ExecutionStep, state: ExecutionPlanState) -> Tuple[bool, ExecutionPlanState]:
        state = self._increment_attempts(state, step.id)
        return self._run_step(step, state)

    def _get_step_state(self, state: ExecutionPlanState, step_id: str) -> StepExecutionState:
        for step_state in state.step_states:
            if step_state.step_id == step_id:
                return step_state
        raise ExecutorError(f"Step state '{step_id}' not found")

    def _mark_step_running(self, state: ExecutionPlanState, step_id: str) -> ExecutionPlanState:
        return self._update_state(state, step_id, PlanStatus.RUNNING.value)

    def _mark_completed(self, state: ExecutionPlanState, step_id: str) -> ExecutionPlanState:
        state = self._update_state(state, step_id, PlanStatus.COMPLETED.value)
        return self._update_progress(state)

    def _mark_failed(self, state: ExecutionPlanState, step_id: str, error: str) -> ExecutionPlanState:
        state = self._update_state(state, step_id, PlanStatus.FAILED.value, last_error=error)
        return self._set_status(state, PlanStatus.FAILED)

    def _mark_canceled(self, state: ExecutionPlanState, reason: str) -> ExecutionPlanState:
        state = self._update_state(state, state.step_states[0].step_id if state.step_states else "", PlanStatus.CANCELED.value, last_error=reason)
        return self._set_status(state, PlanStatus.CANCELED)

    def _increment_attempts(self, state: ExecutionPlanState, step_id: str) -> ExecutionPlanState:
        step_states: List[StepExecutionState] = []
        for step_state in state.step_states:
            if step_state.step_id == step_id:
                step_states.append(
                    StepExecutionState(
                        step_id=step_state.step_id,
                        status=step_state.status,
                        attempts=step_state.attempts + 1,
                        last_error=step_state.last_error,
                        metadata=step_state.metadata,
                    )
                )
            else:
                step_states.append(step_state)
        return ExecutionPlanState(
            plan_id=state.plan_id,
            status=state.status,
            progress=state.progress,
            step_states=tuple(step_states),
            metadata=state.metadata,
        )

    def _calculate_progress(self, state: ExecutionPlanState) -> float:
        completed = sum(1 for s in state.step_states if s.status == PlanStatus.COMPLETED.value)
        return completed / len(state.step_states) if state.step_states else 0.0

    def _update_progress(self, state: ExecutionPlanState) -> ExecutionPlanState:
        return ExecutionPlanState(
            plan_id=state.plan_id,
            status=state.status,
            progress=self._calculate_progress(state),
            step_states=state.step_states,
            metadata=state.metadata,
        )

    def _set_status(self, state: ExecutionPlanState, status: PlanStatus) -> ExecutionPlanState:
        return ExecutionPlanState(
            plan_id=state.plan_id,
            status=status,
            progress=state.progress,
            step_states=state.step_states,
            metadata=state.metadata,
        )

    def _update_state(
        self,
        state: ExecutionPlanState,
        step_id: str,
        status: str,
        last_error: str = "",
    ) -> ExecutionPlanState:
        step_states: List[StepExecutionState] = []
        for step_state in state.step_states:
            if step_state.step_id == step_id:
                step_states.append(
                    StepExecutionState(
                        step_id=step_state.step_id,
                        status=status,
                        attempts=step_state.attempts,
                        last_error=last_error,
                        metadata=step_state.metadata,
                    )
                )
            else:
                step_states.append(step_state)
        return ExecutionPlanState(
            plan_id=state.plan_id,
            status=PlanStatus.RUNNING,
            progress=state.progress,
            step_states=tuple(step_states),
            metadata=state.metadata,
        )
