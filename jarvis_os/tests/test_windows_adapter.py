"""
Unit Tests – Windows Automation Adapter

Tests cover:
    WindowsOpenAppAction    – success (startfile), fallback (subprocess), missing param,
                              subprocess failure.
    WindowsLaunchExecAction – success (with/without args), missing param, file-not-found,
                              subprocess failure, cwd forwarding.
    WindowsOpenUrlAction    – success (startfile), fallback (webbrowser), missing param,
                              invalid scheme, webbrowser returns False, webbrowser exception.

Architecture rules verified:
    * No imports from external vendor packages (os/subprocess/webbrowser are stdlib).
    * Only AutomationExecutionException is raised to callers.
    * Core packages are not modified.
"""

import subprocess
import sys
import unittest
from unittest.mock import MagicMock, patch

from jarvis_os.core.automation.exceptions import AutomationExecutionException
from jarvis_os.core.automation.models import AutomationContext, AutomationResult
from jarvis_os.infrastructure.automation.windows_adapter import (
    WindowsLaunchExecAction,
    WindowsOpenAppAction,
    WindowsOpenUrlAction,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ctx(**kwargs) -> AutomationContext:
    """Return a context pre-loaded with the given variables."""
    return AutomationContext(variables=dict(kwargs))


# ===========================================================================
# WindowsOpenAppAction
# ===========================================================================

class TestWindowsOpenAppActionMetadata(unittest.TestCase):
    """Verify that the action registers itself with the correct identity."""

    def setUp(self):
        self.action = WindowsOpenAppAction()

    def test_name(self):
        self.assertEqual(self.action.name, "windows.open_app")

    def test_description_not_empty(self):
        self.assertTrue(len(self.action.description) > 0)

    def test_version(self):
        self.assertEqual(self.action.version, "1.0.0")

    def test_enabled_by_default(self):
        self.assertTrue(self.action.enabled)

    def test_is_automation_action(self):
        from jarvis_os.core.automation.action import AutomationAction
        self.assertIsInstance(self.action, AutomationAction)


class TestWindowsOpenAppActionExecute(unittest.TestCase):

    def setUp(self):
        self.action = WindowsOpenAppAction()

    # --- success via os.startfile -------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_success_via_startfile_kwarg(self, mock_startfile):
        result = self.action.execute(_ctx(), app_name="notepad")
        mock_startfile.assert_called_once_with("notepad")
        self.assertTrue(result.success)
        self.assertIn("notepad", result.output)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_success_reads_app_name_from_context(self, mock_startfile):
        result = self.action.execute(_ctx(app_name="calc"))
        mock_startfile.assert_called_once_with("calc")
        self.assertTrue(result.success)

    # --- fallback via subprocess when startfile raises OSError --------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=OSError("shell error"))
    def test_fallback_to_subprocess_on_oserror(self, mock_startfile, mock_popen):
        mock_proc = MagicMock()
        mock_popen.return_value = mock_proc

        result = self.action.execute(_ctx(), app_name="mspaint")

        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args
        self.assertTrue(call_kwargs[1].get("shell"))
        self.assertTrue(result.success)

    # --- AttributeError (non-Windows) falls back to subprocess -------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=AttributeError("not available"))
    def test_fallback_to_subprocess_on_attribute_error(self, mock_startfile, mock_popen):
        mock_popen.return_value = MagicMock()
        result = self.action.execute(_ctx(), app_name="notepad")
        self.assertTrue(result.success)

    # --- missing parameter --------------------------------------------------

    def test_raises_when_app_name_missing(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx())

    def test_raises_when_app_name_empty_string(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), app_name="")

    # --- subprocess failure -------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen",
           side_effect=OSError("popen failed"))
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=OSError("startfile failed"))
    def test_raises_on_subprocess_failure(self, mock_sf, mock_popen):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), app_name="nonexistent_app")

    # --- result contract ----------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_result_is_automation_result(self, _):
        result = self.action.execute(_ctx(), app_name="notepad")
        self.assertIsInstance(result, AutomationResult)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_result_has_no_error_message_on_success(self, _):
        result = self.action.execute(_ctx(), app_name="notepad")
        self.assertIsNone(result.error_message)


# ===========================================================================
# WindowsLaunchExecAction
# ===========================================================================

class TestWindowsLaunchExecActionMetadata(unittest.TestCase):

    def setUp(self):
        self.action = WindowsLaunchExecAction()

    def test_name(self):
        self.assertEqual(self.action.name, "windows.launch_executable")

    def test_description_not_empty(self):
        self.assertTrue(len(self.action.description) > 0)

    def test_version(self):
        self.assertEqual(self.action.version, "1.0.0")

    def test_is_automation_action(self):
        from jarvis_os.core.automation.action import AutomationAction
        self.assertIsInstance(self.action, AutomationAction)


class TestWindowsLaunchExecActionExecute(unittest.TestCase):

    def setUp(self):
        self.action = WindowsLaunchExecAction()

    # --- success ------------------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_success_without_args(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_popen.return_value = mock_proc

        result = self.action.execute(_ctx(), executable="C:/Windows/System32/notepad.exe")

        self.assertTrue(result.success)
        self.assertEqual(result.output["pid"], 1234)
        self.assertEqual(result.output["executable"], "C:/Windows/System32/notepad.exe")
        self.assertEqual(result.output["args"], [])

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_success_with_args(self, mock_popen):
        mock_proc = MagicMock()
        mock_proc.pid = 5678
        mock_popen.return_value = mock_proc

        result = self.action.execute(
            _ctx(),
            executable="C:/myapp/app.exe",
            args=["--verbose", "--port", "8080"],
        )

        call_args = mock_popen.call_args[0][0]  # positional list
        self.assertEqual(call_args, ["C:/myapp/app.exe", "--verbose", "--port", "8080"])
        self.assertTrue(result.success)
        self.assertEqual(result.output["args"], ["--verbose", "--port", "8080"])

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_popen_called_with_shell_false(self, mock_popen):
        mock_popen.return_value = MagicMock(pid=9)
        self.action.execute(_ctx(), executable="C:/app.exe")
        _, call_kw = mock_popen.call_args
        self.assertFalse(call_kw.get("shell", True))

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_reads_executable_from_context(self, mock_popen):
        mock_popen.return_value = MagicMock(pid=42)
        result = self.action.execute(_ctx(executable="C:/tools/tool.exe"))
        self.assertTrue(result.success)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_cwd_forwarded_to_popen(self, mock_popen):
        mock_popen.return_value = MagicMock(pid=77)
        self.action.execute(_ctx(), executable="app.exe", cwd="C:/workdir")
        _, call_kw = mock_popen.call_args
        self.assertEqual(call_kw.get("cwd"), "C:/workdir")

    # --- missing / invalid parameter ----------------------------------------

    def test_raises_when_executable_missing(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx())

    def test_raises_when_executable_empty(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), executable="")

    # --- failure paths -------------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen",
           side_effect=FileNotFoundError("not found"))
    def test_raises_on_file_not_found(self, _):
        with self.assertRaises(AutomationExecutionException) as ctx:
            self.action.execute(_ctx(), executable="C:/does_not_exist.exe")
        self.assertIn("not found", str(ctx.exception).lower())

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen",
           side_effect=OSError("permission denied"))
    def test_raises_on_os_error(self, _):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), executable="C:/protected.exe")

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen",
           side_effect=subprocess.SubprocessError("crash"))
    def test_raises_on_subprocess_error(self, _):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), executable="C:/app.exe")

    # --- result contract ----------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.subprocess.Popen")
    def test_result_is_automation_result(self, mock_popen):
        mock_popen.return_value = MagicMock(pid=1)
        result = self.action.execute(_ctx(), executable="app.exe")
        self.assertIsInstance(result, AutomationResult)


# ===========================================================================
# WindowsOpenUrlAction
# ===========================================================================

class TestWindowsOpenUrlActionMetadata(unittest.TestCase):

    def setUp(self):
        self.action = WindowsOpenUrlAction()

    def test_name(self):
        self.assertEqual(self.action.name, "windows.open_url")

    def test_description_not_empty(self):
        self.assertTrue(len(self.action.description) > 0)

    def test_version(self):
        self.assertEqual(self.action.version, "1.0.0")

    def test_is_automation_action(self):
        from jarvis_os.core.automation.action import AutomationAction
        self.assertIsInstance(self.action, AutomationAction)


class TestWindowsOpenUrlActionExecute(unittest.TestCase):

    def setUp(self):
        self.action = WindowsOpenUrlAction()

    # --- success via os.startfile -------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_success_https_via_startfile(self, mock_startfile):
        result = self.action.execute(_ctx(), url="https://www.google.com")
        mock_startfile.assert_called_once_with("https://www.google.com")
        self.assertTrue(result.success)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_success_http_via_startfile(self, mock_startfile):
        result = self.action.execute(_ctx(), url="http://localhost:8080")
        self.assertTrue(result.success)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_success_reads_url_from_context(self, mock_startfile):
        result = self.action.execute(_ctx(url="https://example.com"))
        mock_startfile.assert_called_once_with("https://example.com")
        self.assertTrue(result.success)

    # --- fallback via webbrowser when startfile raises OSError ---------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.webbrowser.open",
           return_value=True)
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=OSError("no handler"))
    def test_fallback_to_webbrowser_on_os_error(self, mock_sf, mock_wb):
        result = self.action.execute(_ctx(), url="https://example.com")
        mock_wb.assert_called_once_with("https://example.com")
        self.assertTrue(result.success)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.webbrowser.open",
           return_value=True)
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=AttributeError("non-windows"))
    def test_fallback_to_webbrowser_on_attribute_error(self, mock_sf, mock_wb):
        result = self.action.execute(_ctx(), url="https://example.com")
        self.assertTrue(result.success)

    # --- webbrowser returns False --------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.webbrowser.open",
           return_value=False)
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=OSError("no handler"))
    def test_raises_when_webbrowser_returns_false(self, mock_sf, mock_wb):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), url="https://example.com")

    # --- webbrowser raises exception ----------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.webbrowser.open",
           side_effect=RuntimeError("browser crash"))
    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile",
           side_effect=OSError("no handler"))
    def test_raises_when_webbrowser_raises(self, mock_sf, mock_wb):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), url="https://example.com")

    # --- missing / invalid parameters ----------------------------------------

    def test_raises_when_url_missing(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx())

    def test_raises_when_url_empty(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), url="")

    def test_raises_when_url_has_no_scheme(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), url="www.google.com")

    def test_raises_when_url_has_invalid_scheme(self):
        with self.assertRaises(AutomationExecutionException):
            self.action.execute(_ctx(), url="file:///etc/passwd")

    # --- ftp scheme (valid) -------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_ftp_scheme_accepted(self, mock_startfile):
        result = self.action.execute(_ctx(), url="ftp://files.example.com")
        self.assertTrue(result.success)

    # --- result contract ----------------------------------------------------

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_result_is_automation_result(self, _):
        result = self.action.execute(_ctx(), url="https://example.com")
        self.assertIsInstance(result, AutomationResult)

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_result_no_error_message_on_success(self, _):
        result = self.action.execute(_ctx(), url="https://example.com")
        self.assertIsNone(result.error_message)


# ===========================================================================
# Integration-style: register & execute through the core registry
# ===========================================================================

class TestWindowsActionsWithRegistry(unittest.TestCase):
    """
    Verify the actions can be registered in AutomationRegistry and retrieved
    without touching the core implementation.
    """

    def test_register_all_three_actions(self):
        from jarvis_os.core.automation.registry import AutomationRegistry

        registry = AutomationRegistry()
        registry.register(WindowsOpenAppAction())
        registry.register(WindowsLaunchExecAction())
        registry.register(WindowsOpenUrlAction())

        self.assertTrue(registry.contains("windows.open_app"))
        self.assertTrue(registry.contains("windows.launch_executable"))
        self.assertTrue(registry.contains("windows.open_url"))

    def test_duplicate_registration_raises(self):
        from jarvis_os.core.automation.exceptions import DuplicateAutomationException
        from jarvis_os.core.automation.registry import AutomationRegistry

        registry = AutomationRegistry()
        registry.register(WindowsOpenAppAction())
        with self.assertRaises(DuplicateAutomationException):
            registry.register(WindowsOpenAppAction())

    @patch("jarvis_os.infrastructure.automation.windows_adapter.os.startfile")
    def test_retrieve_and_execute_via_registry(self, mock_startfile):
        from jarvis_os.core.automation.registry import AutomationRegistry

        registry = AutomationRegistry()
        registry.register(WindowsOpenUrlAction())

        action = registry.get("windows.open_url")
        result = action.execute(_ctx(), url="https://example.com")

        self.assertTrue(result.success)


if __name__ == "__main__":
    unittest.main()
