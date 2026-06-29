"""
Main application window for BHUvi.
"""

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFrame,
    QPushButton,
    QLabel,
    QStatusBar,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        """Initialize main window."""
        super().__init__()
        self.setWindowTitle("BHUvi")
        self.setGeometry(100, 100, 1400, 900)
        self.setMinimumSize(QSize(1200, 700))
        
        # Create central widget and main layout
        central = QWidget()
        self.setCentralWidget(central)
        central.setObjectName("centralWidget")
        
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Create sidebar
        sidebar = self._create_sidebar()
        main_layout.addWidget(sidebar)
        
        # Create central area
        central_area = self._create_central_area()
        main_layout.addWidget(central_area, 1)
        
        # Create status bar
        self._create_status_bar()
    
    def _create_sidebar(self) -> QFrame:
        """Create sidebar with navigation buttons."""
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 20, 0, 20)
        layout.setSpacing(10)
        
        nav_items = ["Chat", "Memory", "Models", "Files", "Settings"]
        
        for item in nav_items:
            btn = QPushButton(item)
            btn.setMinimumHeight(40)
            layout.addWidget(btn)
        
        layout.addStretch()
        
        return sidebar
    
    def _create_central_area(self) -> QFrame:
        """Create central welcome area."""
        central = QFrame()
        central.setObjectName("centralArea")
        
        layout = QVBoxLayout(central)
        layout.setAlignment(Qt.AlignCenter)
        
        # Title
        title = QLabel("Welcome to BHUvi")
        title.setObjectName("welcomeTitle")
        title_font = QFont("Segoe UI", 18, QFont.Bold)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        
        # Subtitle
        subtitle = QLabel("Personal AI Operating System")
        subtitle.setObjectName("welcomeSubtitle")
        subtitle_font = QFont("Segoe UI", 11)
        subtitle.setFont(subtitle_font)
        subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(subtitle)
        
        # Phase indicator
        phase = QLabel("GUI Phase 1")
        phase.setObjectName("welcomePhase")
        phase_font = QFont("Segoe UI", 11)
        phase.setFont(phase_font)
        phase.setAlignment(Qt.AlignCenter)
        layout.addWidget(phase)
        
        layout.addStretch()
        
        return central
    
    def _create_status_bar(self):
        """Create status bar."""
        status_bar = QStatusBar()
        status_bar.showMessage("Ready")
        self.setStatusBar(status_bar)
