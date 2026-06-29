"""
Unit Tests for Jarvis OS Tool Registry
"""
import unittest
import threading
from jarvis_os.core.tools.tool import Tool
from jarvis_os.core.tools.registry import ToolRegistry
from jarvis_os.core.tools.models import ToolContext, ToolResult
from jarvis_os.core.tools.exceptions import DuplicateToolException, ToolNotFoundException


class MockTool(Tool):
    """Simple mock tool for testing."""
    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        return ToolResult(success=True, output="mocked")


class TestToolRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.tool1 = MockTool("calculator", "Adds and subtracts numbers")
        self.tool2 = MockTool("browser", "Automates web browser operations")

    def test_registration_and_lookup(self):
        """Test basic tool registration and retrieval."""
        self.registry.register(self.tool1)
        self.assertTrue(self.registry.contains("calculator"))
        self.assertEqual(self.registry.get("calculator"), self.tool1)

    def test_duplicate_registration_raises_exception(self):
        """Test that registering duplicate names raises DuplicateToolException."""
        self.registry.register(self.tool1)
        with self.assertRaises(DuplicateToolException):
            self.registry.register(self.tool1)

        tool_with_same_name = MockTool("calculator", "Different description")
        with self.assertRaises(DuplicateToolException):
            self.registry.register(tool_with_same_name)

    def test_unregister_tool(self):
        """Test unregistering tools removes them from the registry."""
        self.registry.register(self.tool1)
        self.assertTrue(self.registry.contains("calculator"))
        
        self.registry.unregister("calculator")
        self.assertFalse(self.registry.contains("calculator"))
        with self.assertRaises(ToolNotFoundException):
            self.registry.get("calculator")

    def test_unregister_missing_tool_raises_exception(self):
        """Test that unregistering a non-existent tool raises ToolNotFoundException."""
        with self.assertRaises(ToolNotFoundException):
            self.registry.unregister("unknown_tool")

    def test_get_missing_tool_raises_exception(self):
        """Test retrieving a non-existent tool raises ToolNotFoundException."""
        with self.assertRaises(ToolNotFoundException):
            self.registry.get("unknown_tool")

    def test_list_tools(self):
        """Test listing all tools registered."""
        self.registry.register(self.tool1)
        self.registry.register(self.tool2)
        
        tools = self.registry.list_tools()
        self.assertEqual(len(tools), 2)
        self.assertIn(self.tool1, tools)
        self.assertIn(self.tool2, tools)

    def test_concurrent_registration(self):
        """Test thread-safety when registering tools concurrently."""
        num_threads = 20
        threads = []
        errors = []

        def worker(index):
            try:
                tool = MockTool(f"tool_{index}", f"Description {index}")
                self.registry.register(tool)
            except Exception as e:
                errors.append(e)

        for i in range(num_threads):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Encountered registration errors: {errors}")
        self.assertEqual(len(self.registry.list_tools()), num_threads)


if __name__ == "__main__":
    unittest.main()
