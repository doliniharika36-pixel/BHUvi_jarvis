"""
Professional dark theme for BHUvi desktop application.
"""

# Color Palette
COLOR_BG_PRIMARY = "#0d0d0d"           # Main background
COLOR_BG_SECONDARY = "#1a1a1a"        # Secondary background (panels)
COLOR_BG_TERTIARY = "#252525"         # Tertiary (hover states)
COLOR_TEXT_PRIMARY = "#ffffff"        # Primary text
COLOR_TEXT_SECONDARY = "#b0b0b0"      # Secondary text
COLOR_ACCENT = "#10a37f"              # Accent color (success/interactive)
COLOR_BORDER = "#3a3a3a"              # Borders
COLOR_HOVER = "#2d2d2d"               # Hover states
COLOR_SIDEBAR_BG = "#15151b"          # Sidebar background

# Typography
FONT_FAMILY = "Segoe UI, Arial"
FONT_SIZE_BASE = "11pt"
FONT_SIZE_TITLE = "18pt"
FONT_SIZE_BUTTON = "11pt"

GLOBAL_QSS = """
/* Global Styles */
QMainWindow {{
    background-color: {color_bg_primary};
    color: {color_text_primary};
    border: none;
}}

QWidget {{
    background-color: {color_bg_primary};
    color: {color_text_primary};
}}

QFrame {{
    background-color: {color_bg_primary};
    border: none;
}}

/* Sidebar */
#sidebar {{
    background-color: {color_sidebar_bg};
    border-right: 1px solid {color_border};
}}

/* Buttons */
QPushButton {{
    background-color: transparent;
    color: {color_text_primary};
    border: none;
    border-radius: 4px;
    padding: 10px 15px;
    font-family: {font_family};
    font-size: {font_size_button};
    text-align: left;
    margin: 2px;
}}

QPushButton:hover {{
    background-color: {color_hover};
}}

QPushButton:pressed {{
    background-color: {color_bg_tertiary};
}}

QPushButton:checked {{
    background-color: {color_accent};
    color: {color_bg_primary};
}}

/* Status Bar */
QStatusBar {{
    background-color: {color_bg_secondary};
    color: {color_text_secondary};
    border-top: 1px solid {color_border};
    padding: 5px;
}}

QStatusBar::item {{
    border: none;
    padding: 3px;
}}

/* Central Widget */
#centralWidget {{
    background-color: {color_bg_primary};
}}

/* Labels */
QLabel {{
    color: {color_text_primary};
    background-color: transparent;
    font-family: {font_family};
}}

#welcomeTitle {{
    font-size: {font_size_title};
    font-weight: bold;
    color: {color_text_primary};
}}

#welcomeSubtitle {{
    font-size: {font_size_base};
    color: {color_text_secondary};
}}

#welcomePhase {{
    font-size: {font_size_base};
    color: {color_accent};
}}

/* Scrollbar */
QScrollBar:vertical {{
    background-color: {color_bg_primary};
    width: 12px;
    margin: 0px;
}}

QScrollBar::handle:vertical {{
    background-color: {color_border};
    border-radius: 6px;
    min-height: 20px;
    margin: 2px;
}}

QScrollBar::handle:vertical:hover {{
    background-color: {color_text_secondary};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    border: none;
    background: none;
}}

QScrollBar:horizontal {{
    background-color: {color_bg_primary};
    height: 12px;
    margin: 0px;
}}

QScrollBar::handle:horizontal {{
    background-color: {color_border};
    border-radius: 6px;
    min-width: 20px;
    margin: 2px;
}}

QScrollBar::handle:horizontal:hover {{
    background-color: {color_text_secondary};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    border: none;
    background: none;
}}
""".format(
    color_bg_primary=COLOR_BG_PRIMARY,
    color_bg_secondary=COLOR_BG_SECONDARY,
    color_bg_tertiary=COLOR_BG_TERTIARY,
    color_text_primary=COLOR_TEXT_PRIMARY,
    color_text_secondary=COLOR_TEXT_SECONDARY,
    color_accent=COLOR_ACCENT,
    color_border=COLOR_BORDER,
    color_hover=COLOR_HOVER,
    color_sidebar_bg=COLOR_SIDEBAR_BG,
    font_family=FONT_FAMILY,
    font_size_base=FONT_SIZE_BASE,
    font_size_title=FONT_SIZE_TITLE,
    font_size_button=FONT_SIZE_BUTTON,
)


def apply_theme(app):
    """Apply dark theme to Qt application."""
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_QSS)
