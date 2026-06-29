"""
Jarvis OS Desktop Automation Action Registry
"""
import threading
from typing import Dict, List
from jarvis_os.core.automation.action import AutomationAction
from jarvis_os.core.automation.exceptions import DuplicateAutomationException, AutomationNotFoundException

class AutomationRegistry:
    """Thread-safe registry for managing desktop automation actions in Jarvis OS."""

    def __init__(self):
        self._actions: Dict[str, AutomationAction] = {}
        self._lock = threading.RLock()  # Reentrant lock for safety

    def register(self, action: AutomationAction) -> None:
        """
        Registers a new automation action.
        Raises DuplicateAutomationException if an action with the same name already exists.
        """
        with self._lock:
            if action.name in self._actions:
                raise DuplicateAutomationException(f"Automation action '{action.name}' is already registered.")
            self._actions[action.name] = action

    def unregister(self, name: str) -> None:
        """
        Unregisters an action by name.
        Raises AutomationNotFoundException if the action is not found.
        """
        with self._lock:
            if name not in self._actions:
                raise AutomationNotFoundException(f"Automation action '{name}' not found in registry.")
            del self._actions[name]

    def contains(self, name: str) -> bool:
        """Checks if an automation action is registered by name."""
        with self._lock:
            return name in self._actions

    def get(self, name: str) -> AutomationAction:
        """
        Retrieves a registered action by name.
        Raises AutomationNotFoundException if not found.
        """
        with self._lock:
            if name not in self._actions:
                raise AutomationNotFoundException(f"Automation action '{name}' not found in registry.")
            return self._actions[name]

    def list_actions(self) -> List[AutomationAction]:
        """Returns a copy list of all registered automation actions."""
        with self._lock:
            return list(self._actions.values())
