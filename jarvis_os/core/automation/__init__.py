"""
Jarvis OS Desktop Automation Framework Package
"""

from jarvis_os.core.automation.action import AutomationAction
from jarvis_os.core.automation.registry import AutomationRegistry
from jarvis_os.core.automation.executor import AutomationExecutor
from jarvis_os.core.automation.automation import DesktopAutomationService
from jarvis_os.core.automation.models import (
    AutomationContext,
    AutomationMetadata,
    AutomationRequest,
    AutomationResult,
)
from jarvis_os.core.automation.exceptions import (
    AutomationException,
    AutomationNotFoundException,
    DuplicateAutomationException,
    AutomationExecutionException,
)

__all__ = [
    "AutomationAction",
    "AutomationRegistry",
    "AutomationExecutor",
    "DesktopAutomationService",
    "AutomationContext",
    "AutomationMetadata",
    "AutomationRequest",
    "AutomationResult",
    "AutomationException",
    "AutomationNotFoundException",
    "DuplicateAutomationException",
    "AutomationExecutionException",
]
