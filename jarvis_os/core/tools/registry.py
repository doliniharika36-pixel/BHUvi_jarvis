"""
Jarvis OS Tool Registry
"""
import threading
from typing import Dict, List
from jarvis_os.core.tools.tool import Tool
from jarvis_os.core.tools.exceptions import DuplicateToolException, ToolNotFoundException

class ToolRegistry:
    """Thread-safe registry for managing tools in Jarvis OS."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._lock = threading.Lock()

    def register(self, tool: Tool) -> None:
        """
        Registers a new tool. Throws DuplicateToolException if a tool with 
        the same name is already registered.
        """
        with self._lock:
            if tool.name in self._tools:
                raise DuplicateToolException(f"Tool with name '{tool.name}' is already registered.")
            self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """
        Unregisters a tool by name. Throws ToolNotFoundException if not found.
        """
        with self._lock:
            if name not in self._tools:
                raise ToolNotFoundException(f"Tool with name '{name}' not found in registry.")
            del self._tools[name]

    def get(self, name: str) -> Tool:
        """
        Retrieves a registered tool by name. Throws ToolNotFoundException if not found.
        """
        with self._lock:
            if name not in self._tools:
                raise ToolNotFoundException(f"Tool with name '{name}' not found in registry.")
            return self._tools[name]

    def contains(self, name: str) -> bool:
        """
        Checks if a tool with the given name is registered.
        """
        with self._lock:
            return name in self._tools

    def list_tools(self) -> List[Tool]:
        """
        Returns a copy list of all registered tools.
        """
        with self._lock:
            return list(self._tools.values())
