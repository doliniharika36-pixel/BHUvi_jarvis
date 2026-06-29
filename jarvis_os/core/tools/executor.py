"""
Jarvis OS Tool Executor
"""
from jarvis_os.core.tools.registry import ToolRegistry
from jarvis_os.core.tools.models import ToolRequest, ToolResult
from jarvis_os.core.tools.exceptions import ToolExecutionException, ToolNotFoundException, ToolException

class ToolExecutor:
    """Executes registered tools based on ToolRequests in Jarvis OS."""

    def __init__(self, registry: ToolRegistry):
        self._registry = registry

    def execute(self, request: ToolRequest) -> ToolResult:
        """
        Locates the tool in the registry, verifies it is enabled, and runs it.
        Any execution failures are caught and raised as a ToolExecutionException.
        """
        try:
            tool = self._registry.get(request.tool_name)
        except ToolNotFoundException as e:
            raise ToolExecutionException(f"Cannot execute tool: {str(e)}") from e

        if not tool.enabled:
            raise ToolExecutionException(f"Tool '{request.tool_name}' is currently disabled.")

        try:
            # Execute the tool with context and provided arguments
            result = tool.execute(request.context, **request.arguments)
            if not result.success:
                raise ToolExecutionException(f"Tool '{request.tool_name}' returned a failed result: {result.error_message}")
            return result
        except ToolExecutionException:
            # Let ToolExecutionException bubble up directly
            raise
        except Exception as e:
            # Convert any other internal or unexpected failures to ToolExecutionException
            raise ToolExecutionException(f"Failed to execute tool '{request.tool_name}': {str(e)}") from e
