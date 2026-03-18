from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSpinBox,
)
from PyQt6.QtCore import pyqtSignal, Qt

from src.constants import TRACK_COLORS
from src.ui.theme import BG_PANEL, BG_LIGHTER, TEXT_PRIMARY, TEXT_SECONDARY, BORDER_COLOR


class TrackItem(QFrame):
    """Single track row in the track panel."""

    solo_toggled = pyqtSignal(int, bool)
    mute_toggled = pyqtSignal(int, bool)
    priority_changed = pyqtSignal(int, int)
    remove_clicked = pyqtSignal(int)

    def __init__(self, track_id: int, name: str, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            TrackItem {{
                background-color: {BG_LIGHTER};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
                padding: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        r, g, b = color
        color_dot = QLabel()
        color_dot.setFixedSize(12, 12)
        color_dot.setStyleSheet(
            f"background-color: rgb({r},{g},{b}); border-radius: 6px;"
        )
        top_row.addWidget(color_dot)

        name_label = QLabel(name)
        name_label.setStyleSheet(f"color: {TEXT_PRIMARY}; font-size: 11px;")
        name_label.setToolTip(name)
        top_row.addWidget(name_label, 1)

        btn_remove = QPushButton("x")
        btn_remove.setFixedSize(18, 18)
        btn_remove.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                color: {TEXT_SECONDARY};
                border: none;
                font-size: 12px;
            }}
            QPushButton:hover {{ color: #FF1744; }}
        """)
        btn_remove.clicked.connect(lambda: self.remove_clicked.emit(self.track_id))
        top_row.addWidget(btn_remove)

        layout.addLayout(top_row)

        btn_row = QHBoxLayout()
        self.btn_solo = QPushButton("S")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setFixedSize(24, 20)
        self.btn_solo.setStyleSheet(self._toggle_style("#FFD600"))
        self.btn_solo.toggled.connect(lambda v: self.solo_toggled.emit(self.track_id, v))

        self.btn_mute = QPushButton("M")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(24, 20)
        self.btn_mute.setStyleSheet(self._toggle_style("#FF1744"))
        self.btn_mute.toggled.connect(lambda v: self.mute_toggled.emit(self.track_id, v))

        lbl_pri = QLabel("Pri:")
        lbl_pri.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
        self.spin_priority = QSpinBox()
        self.spin_priority.setRange(0, 10)
        self.spin_priority.setFixedWidth(40)
        self.spin_priority.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_PANEL};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR};
                font-size: 10px;
            }}
        """)
        self.spin_priority.valueChanged.connect(
            lambda v: self.priority_changed.emit(self.track_id, v)
        )

        btn_row.addWidget(self.btn_solo)
        btn_row.addWidget(self.btn_mute)
        btn_row.addStretch()
        btn_row.addWidget(lbl_pri)
        btn_row.addWidget(self.spin_priority)
        layout.addLayout(btn_row)

    @staticmethod
    def _toggle_style(active_color: str) -> str:
        return f"""
            QPushButton {{
                background: {BG_PANEL};
                color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR};
                border-radius: 2px;
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:checked {{
                background: {active_color};
                color: #000;
            }}
        """


class TrackPanel(QWidget):
    """Left sidebar listing all tracks with solo/mute/priority controls."""

    solo_toggled = pyqtSignal(int, bool)
    mute_toggled = pyqtSignal(int, bool)
    priority_changed = pyqtSignal(int, int)
    remove_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(200)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        header = QLabel("TRACKS")
        header.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 11px; padding: 4px;")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

        self._items: dict[int, TrackItem] = {}

    def add_track(self, track_id: int, name: str, color: tuple[int, int, int]):
        item = TrackItem(track_id, name, color)
        item.solo_toggled.connect(self.solo_toggled.emit)
        item.mute_toggled.connect(self.mute_toggled.emit)
        item.priority_changed.connect(self.priority_changed.emit)
        item.remove_clicked.connect(self.remove_clicked.emit)
        self._items[track_id] = item
        self._layout.insertWidget(self._layout.count() - 1, item)

    def remove_track(self, track_id: int):
        if track_id in self._items:
            item = self._items.pop(track_id)
            self._layout.removeWidget(item)
            item.deleteLater()
