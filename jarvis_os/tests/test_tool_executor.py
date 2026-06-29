"""
Unit Tests for Jarvis OS Tool Executor
"""
import unittest
import threading
from jarvis_os.core.tools.tool import Tool
from jarvis_os.core.tools.registry import ToolRegistry
from jarvis_os.core.tools.executor import ToolExecutor
from jarvis_os.core.tools.models import ToolContext, ToolRequest, ToolResult
from jarvis_os.core.tools.exceptions import ToolExecutionException


class SuccessTool(Tool):
    """A tool that always executes successfully and returns its input arguments."""
    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        multiplier = kwargs.get("multiplier", 1)
        base = kwargs.get("base", 10)
        return ToolResult(success=True, output=base * multiplier)


class FailTool(Tool):
    """A tool that returns a failed ToolResult."""
    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        return ToolResult(success=False, error_message="Internal hardware disconnect.")


class ExplodingTool(Tool):
    """A tool that raises a standard Exception during execution."""
    def execute(self, context: ToolContext, **kwargs) -> ToolResult:
        raise ValueError("Critical zero-division error inside calculation logic.")


class TestToolExecutor(unittest.TestCase):

    def setUp(self):
        self.registry = ToolRegistry()
        self.executor = ToolExecutor(self.registry)

        self.success_tool = SuccessTool("calc", "Performs arithmetic")
        self.fail_tool = FailTool("faulty_hardware", "Triggers hardware failures")
        self.exploding_tool = ExplodingTool("broken_logic", "Throws exceptions")

        self.registry.register(self.success_tool)
        self.registry.register(self.fail_tool)
        self.registry.register(self.exploding_tool)

    def test_successful_execution(self):
        """Test successful lookup and execution of a tool."""
        request = ToolRequest("calc", arguments={"multiplier": 5, "base": 20})
        result = self.executor.execute(request)
        self.assertTrue(result.success)
        self.assertEqual(result.output, 100)

    def test_disabled_tool_raises_execution_exception(self):
        """Test that executing a disabled tool raises a ToolExecutionException."""
        self.success_tool.enabled = False
        request = ToolRequest("calc", arguments={"multiplier": 5})
        with self.assertRaises(ToolExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("disabled", str(context.exception))

    def test_missing_tool_raises_execution_exception(self):
        """Test that attempting to execute an unregistered tool raises ToolExecutionException."""
        request = ToolRequest("phantom_tool")
        with self.assertRaises(ToolExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("not found", str(context.exception))

    def test_failed_tool_result_converted_to_execution_exception(self):
        """Test that tools returning success=False raise ToolExecutionException."""
        request = ToolRequest("faulty_hardware")
        with self.assertRaises(ToolExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("returned a failed result", str(context.exception))
        self.assertIn("Internal hardware disconnect.", str(context.exception))

    def test_exploding_tool_converted_to_execution_exception(self):
        """Test that tool code throwing native exceptions is wrapped in ToolExecutionException."""
        request = ToolRequest("broken_logic")
        with self.assertRaises(ToolExecutionException) as context:
            self.executor.execute(request)
        self.assertIn("Failed to execute tool", str(context.exception))
        self.assertIn("Critical zero-division error", str(context.exception))

    def test_concurrent_execution(self):
        """Test executing tools concurrently across multiple threads."""
        num_threads = 30
        threads = []
        errors = []

        def worker(index):
            try:
                request = ToolRequest("calc", arguments={"multiplier": index, "base": 2})
                result = self.executor.execute(request)
                if not result.success or result.output != index * 2:
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
