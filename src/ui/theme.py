import sys

BG_DARK = "#1A1A1A"
BG_PANEL = "#242424"
BG_LIGHTER = "#2E2E2E"
GRID_COLOR = "#333333"
TEXT_PRIMARY = "#E0E0E0"
TEXT_SECONDARY = "#888888"
ACCENT = "#00E5FF"
PLAYHEAD_COLOR = "#FF1744"
BORDER_COLOR = "#3A3A3A"

if sys.platform == "win32":
    MONO_FONT = "Consolas"
elif sys.platform == "darwin":
    MONO_FONT = "SF Mono"
else:
    MONO_FONT = "monospace"

GLOBAL_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_PRIMARY};
    font-family: '{MONO_FONT}', monospace;
    font-size: 12px;
}}
QToolBar {{
    background-color: {BG_PANEL};
    border-bottom: 1px solid {BORDER_COLOR};
    spacing: 6px;
    padding: 4px;
}}
QToolBar QToolButton {{
    background-color: {BG_LIGHTER};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_COLOR};
    border-radius: 3px;
    padding: 4px 12px;
    font-family: '{MONO_FONT}', monospace;
    font-size: 12px;
}}
QToolBar QToolButton:hover {{
    background-color: #3A3A3A;
}}
QToolBar QToolButton:pressed {{
    background-color: {ACCENT};
    color: #000;
}}
QToolBar QToolButton:checked {{
    background-color: {ACCENT};
    color: #000;
}}
QSplitter::handle {{
    background-color: {BORDER_COLOR};
}}
QScrollBar:vertical {{
    background: {BG_PANEL};
    width: 8px;
}}
QScrollBar::handle:vertical {{
    background: #555;
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar:horizontal {{
    background: {BG_PANEL};
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #555;
    border-radius: 4px;
    min-width: 20px;
}}
QLabel {{
    color: {TEXT_PRIMARY};
}}
"""
