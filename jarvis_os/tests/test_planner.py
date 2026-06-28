"""Unit tests for the Planner subsystem."""
import unittest

from jarvis_os.core.planning.models import ExecutionPlan, ExecutionStep
from jarvis_os.core.planning.planner import Planner, PlanningRequest


class TestPlanner(unittest.TestCase):
    def setUp(self) -> None:
        self.planner = Planner()

    def test_plan_creates_execution_plan(self) -> None:
        request = PlanningRequest(goal="Open Chrome and take a screenshot")
        plan = self.planner.plan(request)

        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.goal, request.goal)
        self.assertTrue(any(step.action == "open_chrome" for step in plan.steps))
        self.assertTrue(any(step.action == "screenshot" for step in plan.steps))

    def test_plan_with_unknown_goal_returns_noop_step(self) -> None:
        request = PlanningRequest(goal="Do something without a template")
        plan = self.planner.plan(request)

        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].action, "noop")

    def test_empty_goal_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            self.planner.plan(PlanningRequest(goal="  "))

    def test_plan_id_is_deterministic(self) -> None:
        request = PlanningRequest(goal="Open Chrome")
        plan1 = self.planner.plan(request)
        plan2 = self.planner.plan(request)

        self.assertEqual(plan1.id, plan2.id)
        self.assertEqual(plan1.id, "open_chrome")


if __name__ == "__main__":
    unittest.main()
