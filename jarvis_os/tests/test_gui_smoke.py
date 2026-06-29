"""
Smoke tests for BHUvi GUI.

Verifies basic functionality without backend integration.
"""

import unittest
from PySide6.QtWidgets import QApplication
from jarvis_os.gui.app import BHUviApp
from jarvis_os.gui.windows.main_window import MainWindow
from jarvis_os.gui.styles.dark_theme import apply_theme


class TestGUIAppShell(unittest.TestCase):
    """Smoke tests for GUI application shell."""

    @classmethod
    def setUpClass(cls):
        """Create Qt application once for all tests."""
        cls.qapp = QApplication.instance()
        if cls.qapp is None:
            cls.qapp = QApplication([])

    def test_app_builds(self):
        """Verify Qt application can be built."""
        app = BHUviApp()
        qapp = app.build()
        self.assertIsNotNone(qapp)
        self.assertIsInstance(qapp, QApplication)

    def test_app_has_instance(self):
        """Verify app property returns instance."""
        app = BHUviApp()
        qapp1 = app.app
        qapp2 = app.app
        self.assertIs(qapp1, qapp2)

    def test_theme_applies(self):
        """Verify theme can be applied without errors."""
        app = BHUviApp()
        qapp = app.build()
        # Theme is applied in build()
        self.assertIsNotNone(qapp.styleSheet())

    def test_main_window_creates(self):
        """Verify main window can be created."""
        window = MainWindow()
        self.assertIsNotNone(window)
        self.assertEqual(window.windowTitle(), "BHUvi")

    def test_main_window_size(self):
        """Verify window has correct dimensions."""
        window = MainWindow()
        self.assertEqual(window.width(), 1400)
        self.assertEqual(window.height(), 900)
        self.assertEqual(window.minimumWidth(), 1200)
        self.assertEqual(window.minimumHeight(), 700)

    def test_sidebar_exists(self):
        """Verify sidebar is created in main window."""
        window = MainWindow()
        # Find sidebar frame
        sidebar = None
        for child in window.findChildren(object):
            if hasattr(child, "objectName") and child.objectName() == "sidebar":
                sidebar = child
                break
        self.assertIsNotNone(sidebar, "Sidebar not found in window")

    def test_status_bar_exists(self):
        """Verify status bar exists and displays Ready."""
        window = MainWindow()
        status_bar = window.statusBar()
        self.assertIsNotNone(status_bar)
        # Check that status bar message contains "Ready"
        self.assertIn("Ready", status_bar.currentMessage())

    def test_central_widget_exists(self):
        """Verify central widget is set."""
        window = MainWindow()
        self.assertIsNotNone(window.centralWidget())

    def test_window_no_crash_on_show(self):
        """Verify window can be shown without crashing."""
        window = MainWindow()
        try:
            window.show()
            window.hide()
            # If we get here, no crash occurred
            self.assertTrue(True)
        except Exception as e:
            self.fail(f"Window show() raised exception: {e}")

    def test_dark_theme_colors(self):
        """Verify dark theme has colors defined."""
        from jarvis_os.gui.styles.dark_theme import COLOR_BG_PRIMARY, COLOR_ACCENT
        self.assertEqual(COLOR_BG_PRIMARY, "#0d0d0d")
        self.assertEqual(COLOR_ACCENT, "#10a37f")


if __name__ == "__main__":
    unittest.main()
