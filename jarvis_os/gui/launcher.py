"""
GUI launcher for BHUvi desktop application.
"""

from jarvis_os.gui.app import BHUviApp
from jarvis_os.gui.windows.main_window import MainWindow


def main():
    """Launch BHUvi GUI application."""
    app = BHUviApp()
    app.build()
    
    window = MainWindow()
    window.show()
    
    app.run()


if __name__ == "__main__":
    main()
