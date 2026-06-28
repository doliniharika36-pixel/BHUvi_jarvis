"""Unit tests for the Executor subsystem."""
import unittest

from jarvis_os.core.execution.executor import Executor, ExecutorError
from jarvis_os.core.execution.models import ExecutionPlanState, PlanStatus, StepExecutionState
from jarvis_os.core.planning.models import ExecutionPlan, ExecutionStep


class TestExecutor(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = {
            "open_chrome": lambda step: True,
            "screenshot": lambda step: True,
            "fail_action": lambda step: False,
        }
        self.executor = Executor(self.actions)

    def test_execute_plan_success(self) -> None:
        plan = ExecutionPlan(
            id="plan1",
            goal="Open Chrome and screenshot",
            steps=(
                ExecutionStep(id="step1", description="Open browser", action="open_chrome"),
                ExecutionStep(id="step2", description="Screenshot", action="screenshot", dependencies=("step1",)),
            ),
        )
        state = self.executor.execute(plan)

        self.assertEqual(state.status, PlanStatus.COMPLETED)
        self.assertEqual(state.progress, 1.0)
        self.assertTrue(all(step.status == PlanStatus.COMPLETED.value for step in state.step_states))

    def test_execute_plan_with_failure(self) -> None:
        plan = ExecutionPlan(
            id="plan2",
            goal="Fail step",
            steps=(ExecutionStep(id="step1", description="Fail", action="fail_action"),),
        )
        state = self.executor.execute(plan)

        self.assertEqual(state.status, PlanStatus.FAILED)
        self.assertEqual(state.step_states[0].status, PlanStatus.FAILED.value)

    def test_execute_plan_unknown_action_fails(self) -> None:
        plan = ExecutionPlan(
            id="plan3",
            goal="Unknown action",
            steps=(ExecutionStep(id="step1", description="Unknown", action="missing_action"),),
        )
        state = self.executor.execute(plan)
        self.assertEqual(state.status, PlanStatus.FAILED)
        self.assertIn("unknown action", state.step_states[0].last_error)

    def test_execute_plan_retry(self) -> None:
        attempts = {"count": 0}

        def flaky_action(step):
            attempts["count"] += 1
            return attempts["count"] > 1

        executor = Executor({"flaky": flaky_action})
        plan = ExecutionPlan(
            id="plan4",
            goal="Retry step",
            steps=(ExecutionStep(id="step1", description="Flaky", action="flaky", retry_limit=1),),
        )
        state = executor.execute(plan)

        self.assertEqual(state.status, PlanStatus.COMPLETED)
        self.assertEqual(attempts["count"], 2)

    def test_execute_empty_plan_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.executor.execute(ExecutionPlan(id="plan5", goal="Empty", steps=()))

    def test_step_state_increased_attempts_on_retry(self) -> None:
        attempts = {"count": 0}

        def flaky_action(step):
            attempts["count"] += 1
            return attempts["count"] > 1

        executor = Executor({"flaky": flaky_action})
        plan = ExecutionPlan(
            id="plan6",
            goal="Retry attempts",
            steps=(ExecutionStep(id="step1", description="Flaky", action="flaky", retry_limit=2),),
        )
        state = executor.execute(plan)

        self.assertEqual(state.status, PlanStatus.COMPLETED)
        self.assertTrue(any(step_state.attempts == 1 for step_state in state.step_states))

    def test_cancel_sets_plan_status_canceled(self) -> None:
        plan = ExecutionPlan(
            id="plan7",
            goal="Cancel plan",
            steps=(ExecutionStep(id="step1", description="Pending", action="open_chrome"),),
        )
        initial_state = ExecutionPlanState(
            plan_id=plan.id,
            status=PlanStatus.PENDING,
            progress=0.0,
            step_states=(StepExecutionState(step_id="step1", status=PlanStatus.PENDING.value),),
        )
        canceled_state = self.executor.cancel(initial_state, reason="user requested")
        self.assertEqual(canceled_state.status, PlanStatus.CANCELED)
        self.assertEqual(canceled_state.step_states[0].status, PlanStatus.CANCELED.value)


if __name__ == "__main__":
    unittest.main()
