"""
Jarvis OS Infrastructure – Windows Automation Adapter

Provides three concrete AutomationAction implementations for Windows:

    WindowsOpenAppAction    – Opens a named application via os.startfile / shell.
    WindowsLaunchExecAction – Launches a full executable path via subprocess.Popen.
    WindowsOpenUrlAction    – Opens a URL in the default browser via os.startfile.

Architecture contract
---------------------
* All classes inherit from AutomationAction (core/automation/action.py).
* No pyautogui, no keyboard, no mouse.
* Infrastructure dependencies are fully contained here.
* Domain exceptions from core/automation/exceptions.py are used for all failures.
"""

from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from typing import List, Optional

from jarvis_os.core.automation.action import AutomationAction
from jarvis_os.core.automation.exceptions import AutomationExecutionException
from jarvis_os.core.automation.models import AutomationContext, AutomationResult


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_windows() -> bool:  # pragma: no cover – platform guard only
    return sys.platform.startswith("win")


# ---------------------------------------------------------------------------
# WindowsOpenAppAction
# ---------------------------------------------------------------------------

class WindowsOpenAppAction(AutomationAction):
    """
    Opens a named application (e.g. 'notepad', 'calc') on Windows.

    Kwargs accepted by execute()
    ----------------------------
    app_name : str
        The name or path of the application to open.

    Strategy
    --------
    Uses ``os.startfile`` for .exe names resolvable via PATH, then falls back
    to ``subprocess.Popen`` with ``shell=True`` so that Windows shell
    associations are honoured (e.g. 'notepad', 'calc').
    """

    ACTION_NAME = "windows.open_app"

    def __init__(self) -> None:
        super().__init__(
            name=self.ACTION_NAME,
            description="Open a named Windows application.",
            version="1.0.0",
        )

    # ------------------------------------------------------------------
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        """
        Execute the open-app action.

        Parameters
        ----------
        context : AutomationContext
            Shared automation context (may carry fallback 'app_name').
        app_name : str (kwarg)
            Name or path of the application to open.

        Returns
        -------
        AutomationResult
            success=True on success, success=False with error_message on failure.

        Raises
        ------
        AutomationExecutionException
            If app_name is missing or the application cannot be launched.
        """
        app_name: Optional[str] = kwargs.get("app_name") or context.get("app_name")
        if not app_name:
            raise AutomationExecutionException(
                "WindowsOpenAppAction requires 'app_name' parameter."
            )

        try:
            # Prefer os.startfile for single tokens (e.g. 'notepad')
            os.startfile(app_name)  # type: ignore[attr-defined]
            return AutomationResult(
                success=True,
                output=f"Application '{app_name}' opened successfully.",
            )
        except AttributeError:
            # os.startfile is Windows-only; on other platforms fall through
            pass
        except OSError as exc:
            # startfile failed – try shell=True subprocess as fallback
            pass  # intentional fall-through

        try:
            subprocess.Popen(
                app_name,
                shell=True,  # noqa: S602 – intentional for desktop automation
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return AutomationResult(
                success=True,
                output=f"Application '{app_name}' launched via shell.",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AutomationExecutionException(
                f"Failed to open application '{app_name}': {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# WindowsLaunchExecAction
# ---------------------------------------------------------------------------

class WindowsLaunchExecAction(AutomationAction):
    """
    Launches a fully-qualified executable path with optional arguments.

    Kwargs accepted by execute()
    ----------------------------
    executable : str
        Absolute or relative path to the executable.
    args : list[str], optional
        Additional command-line arguments to pass to the executable.
    cwd : str, optional
        Working directory for the subprocess. Defaults to None (inherit).
    """

    ACTION_NAME = "windows.launch_executable"

    def __init__(self) -> None:
        super().__init__(
            name=self.ACTION_NAME,
            description="Launch a Windows executable with optional arguments.",
            version="1.0.0",
        )

    # ------------------------------------------------------------------
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        """
        Execute the launch-executable action.

        Parameters
        ----------
        context : AutomationContext
            Shared automation context.
        executable : str (kwarg)
            Path to the executable.
        args : list[str] (kwarg, optional)
            Arguments forwarded to the process.
        cwd : str (kwarg, optional)
            Working directory.

        Returns
        -------
        AutomationResult
            success=True and the process PID on success.

        Raises
        ------
        AutomationExecutionException
            If executable is missing or the process cannot start.
        """
        executable: Optional[str] = kwargs.get("executable") or context.get("executable")
        if not executable:
            raise AutomationExecutionException(
                "WindowsLaunchExecAction requires 'executable' parameter."
            )

        args: List[str] = kwargs.get("args") or []
        cwd: Optional[str] = kwargs.get("cwd") or context.get("cwd")

        command = [executable] + args

        try:
            process = subprocess.Popen(
                command,
                shell=False,  # noqa: S603 – explicit list, no shell injection
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=cwd or None,
            )
            return AutomationResult(
                success=True,
                output={
                    "pid": process.pid,
                    "executable": executable,
                    "args": args,
                },
            )
        except FileNotFoundError as exc:
            raise AutomationExecutionException(
                f"Executable not found: '{executable}'"
            ) from exc
        except (OSError, subprocess.SubprocessError) as exc:
            raise AutomationExecutionException(
                f"Failed to launch executable '{executable}': {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# WindowsOpenUrlAction
# ---------------------------------------------------------------------------

class WindowsOpenUrlAction(AutomationAction):
    """
    Opens a URL in the system's default web browser.

    Kwargs accepted by execute()
    ----------------------------
    url : str
        The URL to open (must include scheme, e.g. https://).

    Strategy
    --------
    Primary  : ``os.startfile(url)`` – delegates to Windows shell / default browser.
    Fallback : ``webbrowser.open(url)`` – cross-platform safety net.
    """

    ACTION_NAME = "windows.open_url"

    def __init__(self) -> None:
        super().__init__(
            name=self.ACTION_NAME,
            description="Open a URL in the default Windows browser.",
            version="1.0.0",
        )

    # ------------------------------------------------------------------
    def execute(self, context: AutomationContext, **kwargs) -> AutomationResult:
        """
        Execute the open-URL action.

        Parameters
        ----------
        context : AutomationContext
            Shared automation context (may carry fallback 'url').
        url : str (kwarg)
            The URL to open.

        Returns
        -------
        AutomationResult
            success=True on success, success=False with error_message on failure.

        Raises
        ------
        AutomationExecutionException
            If url is missing or the browser cannot be opened.
        """
        url: Optional[str] = kwargs.get("url") or context.get("url")
        if not url:
            raise AutomationExecutionException(
                "WindowsOpenUrlAction requires 'url' parameter."
            )

        # Validate minimal URL structure
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("ftp://")):
            raise AutomationExecutionException(
                f"Invalid URL scheme for '{url}'. Expected http://, https://, or ftp://."
            )

        try:
            os.startfile(url)  # type: ignore[attr-defined]
            return AutomationResult(
                success=True,
                output=f"URL '{url}' opened in default browser.",
            )
        except AttributeError:
            # os.startfile not available (non-Windows) – use webbrowser
            pass
        except OSError:
            # startfile failed – fall through to webbrowser
            pass

        try:
            opened = webbrowser.open(url)
            if not opened:
                raise AutomationExecutionException(
                    f"webbrowser.open returned False for URL: '{url}'"
                )
            return AutomationResult(
                success=True,
                output=f"URL '{url}' opened via webbrowser module.",
            )
        except AutomationExecutionException:
            raise
        except Exception as exc:
            raise AutomationExecutionException(
                f"Failed to open URL '{url}': {exc}"
            ) from exc
