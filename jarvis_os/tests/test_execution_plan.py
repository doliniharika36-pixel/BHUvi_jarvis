"""Unit tests for ExecutionPlan models."""
import unittest

from jarvis_os.core.execution.models import ExecutionPlanState, PlanStatus, StepExecutionState


class TestExecutionPlanModels(unittest.TestCase):
    def test_initial_state_has_pending_status(self) -> None:
        state = ExecutionPlanState(
            plan_id="plan1",
            status=PlanStatus.PENDING,
            progress=0.0,
            step_states=(StepExecutionState(step_id="s1", status=PlanStatus.PENDING.value),),
        )
        self.assertEqual(state.status, PlanStatus.PENDING)
        self.assertEqual(state.progress, 0.0)
        self.assertEqual(state.step_states[0].status, PlanStatus.PENDING.value)

    def test_step_execution_state_immutable(self) -> None:
        state = StepExecutionState(step_id="s1", status=PlanStatus.PENDING.value)
        with self.assertRaises(AttributeError):
            state.step_id = "s2"

    def test_plan_state_immutable(self) -> None:
        state = ExecutionPlanState(
            plan_id="plan2",
            status=PlanStatus.PENDING,
            progress=0.0,
            step_states=(StepExecutionState(step_id="s1", status=PlanStatus.PENDING.value),),
        )
        with self.assertRaises(AttributeError):
            state.progress = 1.0


if __name__ == "__main__":
    unittest.main()
