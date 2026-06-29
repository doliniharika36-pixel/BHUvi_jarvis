"""
Jarvis OS Desktop Automation Executor
"""
from jarvis_os.core.automation.registry import AutomationRegistry
from jarvis_os.core.automation.models import AutomationRequest, AutomationResult
from jarvis_os.core.automation.exceptions import AutomationExecutionException, AutomationNotFoundException

class AutomationExecutor:
    """Executes registered desktop automation actions based on AutomationRequests."""

    def __init__(self, registry: AutomationRegistry):
        self._registry = registry

    def execute(self, request: AutomationRequest) -> AutomationResult:
        """
        Locates the automation action, checks if it is enabled, and executes it.
        Any errors are caught and converted to an AutomationExecutionException.
        """
        try:
            action = self._registry.get(request.action_name)
        except AutomationNotFoundException as e:
            raise AutomationExecutionException(f"Cannot execute automation: {str(e)}") from e

        if not action.enabled:
            raise AutomationExecutionException(f"Automation action '{request.action_name}' is currently disabled.")

        try:
            # Run action with parameters
            result = action.execute(request.context, **request.parameters)
            if not result.success:
                raise AutomationExecutionException(f"Automation action '{request.action_name}' failed: {result.error_message}")
            return result
        except AutomationExecutionException:
            # Re-raise explicit execution exceptions
            raise
        except Exception as e:
            # Wrap any unhandled target code exceptions
            raise AutomationExecutionException(f"Failed to execute automation action '{request.action_name}': {str(e)}") from e
