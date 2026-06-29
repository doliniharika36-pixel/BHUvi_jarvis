"""
Qt application wrapper for BHUvi.
"""

from PySide6.QtWidgets import QApplication
from jarvis_os.gui.styles.dark_theme import apply_theme


class BHUviApp:
    """Wrapper for Qt application."""

    def __init__(self):
        """Initialize application wrapper."""
        self.qapp = None

    def build(self) -> QApplication:
        """Build and configure Qt application."""
        if self.qapp is None:
            self.qapp = QApplication.instance()
            if self.qapp is None:
                self.qapp = QApplication([])
            apply_theme(self.qapp)
        return self.qapp

    def run(self):
        """Run the application event loop."""
        if self.qapp is None:
            self.build()
        self.qapp.exec()

    @property
    def app(self) -> QApplication:
        """Get Qt application instance."""
        if self.qapp is None:
            self.build()
        return self.qapp
