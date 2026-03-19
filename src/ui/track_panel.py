import math

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSpinBox, QDoubleSpinBox,
)
from PyQt6.QtCore import pyqtSignal, Qt

from src.ui.theme import (
    BG_PANEL, BG_LIGHTER, TEXT_PRIMARY, TEXT_SECONDARY, BORDER_COLOR, ACCENT,
)


class TrackItem(QFrame):
    """Per-track control container with coordinate inputs, keyframe and recording controls."""

    solo_toggled     = pyqtSignal(int, bool)
    mute_toggled     = pyqtSignal(int, bool)
    priority_changed = pyqtSignal(int, int)
    remove_clicked   = pyqtSignal(int)
    # Emits internal coordinates: ix=pos[0] (X right/left),
    #   iy=pos[1] (internal Y = user's Z front/back),
    #   iz=pos[2] (internal Z = user's Y height)
    coord_changed    = pyqtSignal(int, float, float, float)
    keyframe_requested = pyqtSignal(int)   # track_id
    rec_toggled      = pyqtSignal(int, bool)  # track_id, active

    def __init__(self, track_id: int, name: str, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self._updating = False  # guard against feedback loops

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(f"""
            TrackItem {{
                background-color: {BG_LIGHTER};
                border: 1px solid {BORDER_COLOR};
                border-radius: 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(3)

        # ── Top row: color swatch · name · remove ──
        top_row = QHBoxLayout()
        top_row.setSpacing(5)
        r, g, b = color
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color: rgb({r},{g},{b}); border-radius: 5px;")
        top_row.addWidget(dot)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-size: 11px; font-weight: bold;"
        )
        name_lbl.setToolTip(name)
        top_row.addWidget(name_lbl, 1)

        btn_rm = QPushButton("✕")
        btn_rm.setFixedSize(16, 16)
        btn_rm.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {TEXT_SECONDARY};
                border: none; font-size: 10px;
            }}
            QPushButton:hover {{ color: #FF1744; }}
        """)
        btn_rm.clicked.connect(lambda: self.remove_clicked.emit(self.track_id))
        top_row.addWidget(btn_rm)
        layout.addLayout(top_row)

        # ── Control row: S  M  ●REC  +KF  ···  P: [n] ──
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(3)

        self.btn_solo = QPushButton("S")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setFixedSize(22, 18)
        self.btn_solo.setStyleSheet(self._toggle_style("#FFD600"))
        self.btn_solo.toggled.connect(lambda v: self.solo_toggled.emit(self.track_id, v))

        self.btn_mute = QPushButton("M")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(22, 18)
        self.btn_mute.setStyleSheet(self._toggle_style("#FF1744"))
        self.btn_mute.toggled.connect(lambda v: self.mute_toggled.emit(self.track_id, v))

        self.btn_rec = QPushButton("● REC")
        self.btn_rec.setCheckable(True)
        self.btn_rec.setFixedHeight(18)
        self.btn_rec.setStyleSheet(self._toggle_style("#FF1744"))
        self.btn_rec.toggled.connect(lambda v: self.rec_toggled.emit(self.track_id, v))

        self.btn_kf = QPushButton("+KF")
        self.btn_kf.setFixedHeight(18)
        self.btn_kf.setStyleSheet(f"""
            QPushButton {{
                background: {BG_PANEL}; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR}; border-radius: 2px;
                font-size: 9px; font-weight: bold;
            }}
            QPushButton:hover  {{ background: {ACCENT}; color: #000; }}
            QPushButton:pressed {{ background: #00B8D4; color: #000; }}
        """)
        self.btn_kf.clicked.connect(lambda: self.keyframe_requested.emit(self.track_id))

        lbl_pri = QLabel("P:")
        lbl_pri.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 9px;")
        self.spin_priority = QSpinBox()
        self.spin_priority.setRange(0, 10)
        self.spin_priority.setFixedSize(34, 18)
        self.spin_priority.setStyleSheet(f"""
            QSpinBox {{
                background: {BG_PANEL}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR}; font-size: 9px;
            }}
        """)
        self.spin_priority.valueChanged.connect(
            lambda v: self.priority_changed.emit(self.track_id, v)
        )

        ctrl_row.addWidget(self.btn_solo)
        ctrl_row.addWidget(self.btn_mute)
        ctrl_row.addWidget(self.btn_rec)
        ctrl_row.addWidget(self.btn_kf)
        ctrl_row.addStretch()
        ctrl_row.addWidget(lbl_pri)
        ctrl_row.addWidget(self.spin_priority)
        layout.addLayout(ctrl_row)

        # ── Expand/collapse button for coordinate section ──
        self.btn_expand = QPushButton("▶  坐标控制")
        self.btn_expand.setCheckable(True)
        self.btn_expand.setFixedHeight(18)
        self.btn_expand.setStyleSheet(f"""
            QPushButton {{
                background: {BG_PANEL}; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR}; border-radius: 2px;
                font-size: 9px; text-align: left; padding-left: 4px;
            }}
            QPushButton:checked {{ color: {TEXT_PRIMARY}; border-color: {ACCENT}; }}
        """)
        self.btn_expand.toggled.connect(self._on_expand_toggled)
        layout.addWidget(self.btn_expand)

        # ── Coordinate input container (hidden until expanded) ──
        self.coord_widget = QWidget()
        c_layout = QVBoxLayout(self.coord_widget)
        c_layout.setContentsMargins(0, 2, 0, 0)
        c_layout.setSpacing(2)

        spin_style = f"""
            QDoubleSpinBox {{
                background: {BG_PANEL}; color: {TEXT_PRIMARY};
                border: 1px solid {BORDER_COLOR}; font-size: 10px; padding: 1px;
            }}
            QDoubleSpinBox:focus {{ border-color: {ACCENT}; }}
        """

        def _row(label_text, spin):
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: 10px;")
            lbl.setFixedWidth(56)
            row.addWidget(lbl)
            row.addWidget(spin)
            return row

        # X  Right (+) / Left (-)  →  internal pos[0]
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-20.0, 20.0)
        self.spin_x.setSingleStep(0.1)
        self.spin_x.setDecimals(3)
        self.spin_x.setFixedHeight(20)
        self.spin_x.setStyleSheet(spin_style)
        self.spin_x.valueChanged.connect(self._on_xyz_changed)
        c_layout.addLayout(_row("X  L/R:", self.spin_x))

        # Z  Front (+) / Back (-)  →  internal pos[1]  (user labels as Z)
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-20.0, 20.0)
        self.spin_z.setSingleStep(0.1)
        self.spin_z.setDecimals(3)
        self.spin_z.setFixedHeight(20)
        self.spin_z.setStyleSheet(spin_style)
        self.spin_z.valueChanged.connect(self._on_xyz_changed)
        c_layout.addLayout(_row("Z  F/B:", self.spin_z))

        # Y  Height  →  internal pos[2]  (user labels as Y)
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-10.0, 10.0)
        self.spin_y.setSingleStep(0.1)
        self.spin_y.setDecimals(3)
        self.spin_y.setFixedHeight(20)
        self.spin_y.setStyleSheet(spin_style)
        self.spin_y.valueChanged.connect(self._on_xyz_changed)
        c_layout.addLayout(_row("Y  高度:", self.spin_y))

        # Distance  (3D distance from origin, linked to gain)
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.0, 30.0)
        self.spin_dist.setSingleStep(0.1)
        self.spin_dist.setDecimals(3)
        self.spin_dist.setFixedHeight(20)
        self.spin_dist.setStyleSheet(spin_style)
        self.spin_dist.valueChanged.connect(self._on_polar_changed)
        c_layout.addLayout(_row("Dist:", self.spin_dist))

        # Angle  (horizontal azimuth from front, linked to pan)
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(-180.0, 180.0)
        self.spin_angle.setSingleStep(1.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setSuffix("°")
        self.spin_angle.setWrapping(True)
        self.spin_angle.setFixedHeight(20)
        self.spin_angle.setStyleSheet(spin_style)
        self.spin_angle.valueChanged.connect(self._on_polar_changed)
        c_layout.addLayout(_row("Angle:", self.spin_angle))

        self.coord_widget.setVisible(False)
        layout.addWidget(self.coord_widget)

    # ── Expand toggle ─────────────────────────────────────────────

    def _on_expand_toggled(self, checked: bool):
        self.btn_expand.setText(("▼" if checked else "▶") + "  坐标控制")
        self.coord_widget.setVisible(checked)

    # ── Spinbox change handlers ───────────────────────────────────

    def _on_xyz_changed(self):
        if self._updating:
            return
        ix = self.spin_x.value()
        iy = self.spin_z.value()   # user's Z → internal Y (front/back)
        iz = self.spin_y.value()   # user's Y → internal Z (height)

        self._updating = True
        dist = math.sqrt(ix * ix + iy * iy + iz * iz)
        angle = math.degrees(math.atan2(ix, iy)) if (abs(ix) > 1e-9 or abs(iy) > 1e-9) else 0.0
        self.spin_dist.setValue(dist)
        self.spin_angle.setValue(angle)
        self._updating = False

        self.coord_changed.emit(self.track_id, ix, iy, iz)

    def _on_polar_changed(self):
        if self._updating:
            return
        dist = self.spin_dist.value()
        angle_rad = math.radians(self.spin_angle.value())
        ix = dist * math.sin(angle_rad)
        iy = dist * math.cos(angle_rad)   # internal Y = user's Z
        iz = self.spin_y.value()          # height unchanged

        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)
        self._updating = False

        self.coord_changed.emit(self.track_id, ix, iy, iz)

    # ── Public API ────────────────────────────────────────────────

    def set_position(self, ix: float, iy: float, iz: float):
        """Programmatically set spinboxes from internal coordinates without emitting coord_changed."""
        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)   # user Z = internal Y
        self.spin_y.setValue(iz)   # user Y = internal Z
        dist = math.sqrt(ix * ix + iy * iy + iz * iz)
        angle = math.degrees(math.atan2(ix, iy)) if (abs(ix) > 1e-9 or abs(iy) > 1e-9) else 0.0
        self.spin_dist.setValue(dist)
        self.spin_angle.setValue(angle)
        self._updating = False

    def is_rec_active(self) -> bool:
        return self.btn_rec.isChecked()

    def stop_recording(self):
        """Programmatically deactivate the rec button (triggers rec_toggled signal)."""
        if self.btn_rec.isChecked():
            self.btn_rec.setChecked(False)

    # ── Style helper ──────────────────────────────────────────────

    @staticmethod
    def _toggle_style(active_color: str) -> str:
        return f"""
            QPushButton {{
                background: {BG_PANEL}; color: {TEXT_SECONDARY};
                border: 1px solid {BORDER_COLOR}; border-radius: 2px;
                font-size: 9px; font-weight: bold;
            }}
            QPushButton:checked {{ background: {active_color}; color: #000; }}
        """


class TrackPanel(QWidget):
    """Left sidebar: one TrackItem per audio track with full spatial control."""

    solo_toggled       = pyqtSignal(int, bool)
    mute_toggled       = pyqtSignal(int, bool)
    priority_changed   = pyqtSignal(int, int)
    remove_clicked     = pyqtSignal(int)
    coord_changed      = pyqtSignal(int, float, float, float)  # tid, ix, iy, iz
    keyframe_requested = pyqtSignal(int)                       # tid
    rec_toggled        = pyqtSignal(int, bool)                 # tid, active

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(290)
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
        item.coord_changed.connect(self.coord_changed.emit)
        item.keyframe_requested.connect(self.keyframe_requested.emit)
        item.rec_toggled.connect(self.rec_toggled.emit)
        self._items[track_id] = item
        self._layout.insertWidget(self._layout.count() - 1, item)

    def remove_track(self, track_id: int):
        if track_id in self._items:
            item = self._items.pop(track_id)
            self._layout.removeWidget(item)
            item.deleteLater()

    def set_track_position(self, track_id: int, ix: float, iy: float, iz: float):
        """Update coordinate spinboxes during playback (no signal emitted)."""
        if track_id in self._items:
            self._items[track_id].set_position(ix, iy, iz)

    def get_rec_tracks(self) -> set[int]:
        return {tid for tid, item in self._items.items() if item.is_rec_active()}

    def stop_all_recording(self):
        """Deactivate all rec buttons (each emits rec_toggled)."""
        for item in self._items.values():
            item.stop_recording()
