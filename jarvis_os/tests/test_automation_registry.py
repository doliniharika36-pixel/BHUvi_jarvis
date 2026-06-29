"""
Unit Tests for Jarvis OS Desktop Automation Action Registry
"""
import unittest
import threading
from jarvis_os.core.automation.action import AutomationAction
from jarvis_os.core.automation.registry import AutomationRegistry
from jarvis_os.core.automation.models import AutomationContext, AutomationResult
from jarvis_os.core.automation.exceptions import DuplicateAutomationException, AutomationNotFoundException


class MockAutomationAction(AutomationAction):
    """Simple mock action for testing registry behaviors."""
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        return AutomationResult(success=True, output="mocked")


class TestAutomationRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = AutomationRegistry()
        self.action1 = MockAutomationAction("click_button", "Simulates left-clicking on coordinates")
        self.action2 = MockAutomationAction("type_text", "Types text into active focal element")

    def test_registration_and_lookup(self):
        """Test registering and retrieving actions."""
        self.registry.register(self.action1)
        self.assertTrue(self.registry.contains("click_button"))
        self.assertEqual(self.registry.get("click_button"), self.action1)

    def test_duplicate_registration_raises_exception(self):
        """Test that registering duplicate action names raises DuplicateAutomationException."""
        self.registry.register(self.action1)
        with self.assertRaises(DuplicateAutomationException):
            self.registry.register(self.action1)

        another_action_same_name = MockAutomationAction("click_button", "Some distinct help text")
        with self.assertRaises(DuplicateAutomationException):
            self.registry.register(another_action_same_name)

    def test_unregister_action(self):
        """Test unregistering an action correctly clears it from the index."""
        self.registry.register(self.action1)
        self.assertTrue(self.registry.contains("click_button"))

        self.registry.unregister("click_button")
        self.assertFalse(self.registry.contains("click_button"))
        with self.assertRaises(AutomationNotFoundException):
            self.registry.get("click_button")

    def test_unregister_missing_action_raises_exception(self):
        """Test unregistering a non-existent action raises AutomationNotFoundException."""
        with self.assertRaises(AutomationNotFoundException):
            self.registry.unregister("unknown_action")

    def test_get_missing_action_raises_exception(self):
        """Test retrieving a non-existent action raises AutomationNotFoundException."""
        with self.assertRaises(AutomationNotFoundException):
            self.registry.get("unknown_action")

    def test_list_actions(self):
        """Test listing all active registered actions."""
        self.registry.register(self.action1)
        self.registry.register(self.action2)

        actions = self.registry.list_actions()
        self.assertEqual(len(actions), 2)
        self.assertIn(self.action1, actions)
        self.assertIn(self.action2, actions)

    def test_concurrent_registration_thread_safety(self):
        """Test that concurrent action registrations are thread-safe and maintain registry integrity."""
        num_threads = 25
        threads = []
        errors = []

        def worker(index):
            try:
                action = MockAutomationAction(f"action_{index}", f"Automates sequence {index}")
                self.registry.register(action)
            except Exception as e:
                errors.append(e)

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered registry thread contention errors: {errors}")
        self.assertEqual(len(self.registry.list_actions()), num_threads)


if __name__ == "__main__":
    unittest.main()
