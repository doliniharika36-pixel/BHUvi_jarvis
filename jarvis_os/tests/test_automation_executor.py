"""
Unit Tests for Jarvis OS Desktop Automation Action Executor
"""
import unittest
import threading
from jarvis_os.core.automation.action import AutomationAction
from jarvis_os.core.automation.registry import AutomationRegistry
from jarvis_os.core.automation.executor import AutomationExecutor
from jarvis_os.core.automation.models import AutomationContext, AutomationRequest, AutomationResult
from jarvis_os.core.automation.exceptions import AutomationExecutionException


class SuccessAction(AutomationAction):
    """An action that finishes successfully, multiplying or transforming arguments."""
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        multiplier = kwargs.get("multiplier", 1)
        base = kwargs.get("base", 100)
        return AutomationResult(success=True, output=base * multiplier)


class FailingAction(AutomationAction):
    """An action that returns a failed AutomationResult."""
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        return AutomationResult(success=False, error_message="UI component coordinates off-screen.")


class ExplodingAction(AutomationAction):
    """An action that crashes with an unhandled exception inside execute."""
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        raise OSError("Win32 API connection lost during DLL invocation.")


class TestAutomationExecutor(unittest.TestCase):

    def setUp(self):
        self.registry = AutomationRegistry()
        self.executor = AutomationExecutor(self.registry)

        self.success_action = SuccessAction("calc_pos", "Calculates coordinate mapping offsets")
        self.failing_action = FailingAction("click_target", "Interacts with clickable bounds")
        self.exploding_action = ExplodingAction("sys_ioctl", "Interacts with low-level platform registers")

        self.registry.register(self.success_action)
        self.registry.register(self.failing_action)
        self.registry.register(self.exploding_action)

    def test_successful_execution(self):
        """Test successful lookup and execution of an action."""
        request = AutomationRequest("calc_pos", parameters={"multiplier": 3, "base": 50})
        result = self.executor.execute(request)
        self.assertTrue(result.success)
        self.assertEqual(result.output, 150)

    def test_disabled_action_raises_execution_exception(self):
        """Test that executing a disabled action raises an AutomationExecutionException."""
        self.success_action.enabled = False
        request = AutomationRequest("calc_pos")
        with self.assertRaises(AutomationExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("disabled", str(context.exception))

    def test_missing_action_raises_execution_exception(self):
        """Test that executing an unregistered action name raises AutomationExecutionException."""
        request = AutomationRequest("phantom_automation")
        with self.assertRaises(AutomationExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("not found", str(context.exception))

    def test_failed_result_converted_to_execution_exception(self):
        """Test that actions returning success=False raise AutomationExecutionException."""
        request = AutomationRequest("click_target")
        with self.assertRaises(AutomationExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("failed", str(context.exception))
        self.assertIn("off-screen", str(context.exception))

    def test_exploding_code_wrapped_in_execution_exception(self):
        """Test that code throwing unhandled exceptions inside actions is caught and wrapped in AutomationExecutionException."""
        request = AutomationRequest("sys_ioctl")
        with self.assertRaises(AutomationExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("Failed to execute automation", str(context.exception))
        self.assertIn("Win32 API connection lost", str(context.exception))

    def test_concurrent_action_execution_safety(self):
        """Test executing actions concurrently across multiple threads is completely thread-safe."""
        num_threads = 30
        threads = []
        errors = []

        def worker(index):
            try:
                request = AutomationRequest("calc_pos", parameters={"multiplier": index, "base": 5})
                result = self.executor.execute(request)
                if not result.success or result.output != index * 5:
                    errors.append(f"Thread {index} got wrong result: {result.output}")
            except Exception as e:
                errors.append(f"Thread {index} failed with exception: {e}")

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered concurrent execution errors: {errors}")


if __name__ == "__main__":
    unittest.main()
