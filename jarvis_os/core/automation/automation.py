"""
Jarvis OS Desktop Automation Unified Orchestrator
"""
from typing import Dict, Any, Optional
from jarvis_os.core.automation.registry import AutomationRegistry
from jarvis_os.core.automation.executor import AutomationExecutor
from jarvis_os.core.automation.models import AutomationRequest, AutomationResult, AutomationContext
from jarvis_os.core.automation.action import AutomationAction

class DesktopAutomationService:
    """
    A unified entry-point orchestrator that ties the AutomationRegistry 
    and AutomationExecutor together for simple, single-point calls.
    """

    def __init__(self, registry: Optional[AutomationRegistry] = None, executor: Optional[AutomationExecutor] = None):
        self.registry = registry if registry is not None else AutomationRegistry()
        self.executor = executor if executor is not None else AutomationExecutor(self.registry)

    def register_action(self, action: AutomationAction) -> None:
        """Register an automation action."""
        self.registry.register(action)

    def unregister_action(self, name: str) -> None:
        """Unregister an automation action by name."""
        self.registry.unregister(name)

    def execute_action(self, name: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[AutomationContext] = None) -> AutomationResult:
        """Constructs an AutomationRequest and executes the target action."""
        request = AutomationRequest(action_name=name, parameters=parameters, context=context)
        return self.executor.execute(request)
