"""
Track Panel – left sidebar with per-track controls.

Each TrackItem contains:
  • Top row    : colour dot · name · remove (✕)
  • Control row: S (solo) · M (mute) · ● REC · +KF · priority
  • SpatialPad : 2D XZ bird's-eye positioning pad (always visible)
  • Expand ▶   : detailed coordinate spinboxes (X / Z / Y / Dist / Angle)
"""

import math
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSpinBox, QDoubleSpinBox,
)
from PyQt6.QtCore import pyqtSignal, Qt

from src.ui.theme import (
    BG_PANEL, BG_LIGHTER, TEXT_PRIMARY, TEXT_SECONDARY, BORDER_COLOR, ACCENT,
)
from src.ui.spatial_pad import SpatialPad


class TrackItem(QFrame):
    """Per-track control panel integrating SpatialPad and coordinate spinboxes."""

    solo_toggled       = pyqtSignal(int, bool)
    mute_toggled       = pyqtSignal(int, bool)
    priority_changed   = pyqtSignal(int, int)
    remove_clicked     = pyqtSignal(int)
    # Internal coords: ix=X, iy=internal-Y (user Z front/back), iz=internal-Z (user Y height)
    coord_changed      = pyqtSignal(int, float, float, float)
    keyframe_requested = pyqtSignal(int)    # track_id
    rec_toggled        = pyqtSignal(int, bool)   # track_id, active

    def __init__(self, track_id: int, name: str, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self._color = color
        self._updating = False

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

        # ── Top row ──────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(5)
        r, g, b = color
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background-color:rgb({r},{g},{b}); border-radius:5px;")
        top.addWidget(dot)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;")
        name_lbl.setToolTip(name)
        top.addWidget(name_lbl, 1)

        btn_rm = QPushButton("✕")
        btn_rm.setFixedSize(16, 16)
        btn_rm.setStyleSheet(f"""
            QPushButton {{ background:transparent; color:{TEXT_SECONDARY};
                           border:none; font-size:10px; }}
            QPushButton:hover {{ color:#FF1744; }}
        """)
        btn_rm.clicked.connect(lambda: self.remove_clicked.emit(self.track_id))
        top.addWidget(btn_rm)
        layout.addLayout(top)

        # ── Control row ───────────────────────────────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(3)

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
        self.btn_rec.toggled.connect(self._on_rec_toggled)

        self.btn_kf = QPushButton("+KF")
        self.btn_kf.setFixedHeight(18)
        self.btn_kf.setToolTip("在当前播放时刻为此音轨添加关键帧\n快捷键: 拖动 SpatialPad 时按住会连续记录轨迹")
        self.btn_kf.setStyleSheet(f"""
            QPushButton {{ background:{BG_PANEL}; color:{TEXT_SECONDARY};
                           border:1px solid {BORDER_COLOR}; border-radius:2px;
                           font-size:9px; font-weight:bold; }}
            QPushButton:hover  {{ background:{ACCENT}; color:#000; }}
            QPushButton:pressed {{ background:#00B8D4; color:#000; }}
        """)
        self.btn_kf.clicked.connect(lambda: self.keyframe_requested.emit(self.track_id))

        lbl_pri = QLabel("P:")
        lbl_pri.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:9px;")
        self.spin_priority = QSpinBox()
        self.spin_priority.setRange(0, 10)
        self.spin_priority.setFixedSize(34, 18)
        self.spin_priority.setStyleSheet(f"""
            QSpinBox {{ background:{BG_PANEL}; color:{TEXT_PRIMARY};
                        border:1px solid {BORDER_COLOR}; font-size:9px; }}
        """)
        self.spin_priority.valueChanged.connect(
            lambda v: self.priority_changed.emit(self.track_id, v)
        )

        ctrl.addWidget(self.btn_solo)
        ctrl.addWidget(self.btn_mute)
        ctrl.addWidget(self.btn_rec)
        ctrl.addWidget(self.btn_kf)
        ctrl.addStretch()
        ctrl.addWidget(lbl_pri)
        ctrl.addWidget(self.spin_priority)
        layout.addLayout(ctrl)

        # ── SpatialPad ────────────────────────────────────────────
        self.pad = SpatialPad(track_id, color)
        self.pad.position_changed.connect(self._on_pad_position)
        layout.addWidget(self.pad)

        # ── Expand / coordinate spinboxes ────────────────────────
        self.btn_expand = QPushButton("▶  坐标精确控制")
        self.btn_expand.setCheckable(True)
        self.btn_expand.setFixedHeight(18)
        self.btn_expand.setStyleSheet(f"""
            QPushButton {{ background:{BG_PANEL}; color:{TEXT_SECONDARY};
                           border:1px solid {BORDER_COLOR}; border-radius:2px;
                           font-size:9px; text-align:left; padding-left:4px; }}
            QPushButton:checked {{ color:{TEXT_PRIMARY}; border-color:{ACCENT}; }}
        """)
        self.btn_expand.toggled.connect(self._on_expand)
        layout.addWidget(self.btn_expand)

        self.coord_widget = QWidget()
        cl = QVBoxLayout(self.coord_widget)
        cl.setContentsMargins(0, 2, 0, 0)
        cl.setSpacing(2)

        spin_style = f"""
            QDoubleSpinBox {{ background:{BG_PANEL}; color:{TEXT_PRIMARY};
                              border:1px solid {BORDER_COLOR}; font-size:10px; padding:1px; }}
            QDoubleSpinBox:focus {{ border-color:{ACCENT}; }}
        """

        def _row(label_text, spin):
            row = QHBoxLayout()
            row.setSpacing(4)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px;")
            lbl.setFixedWidth(60)
            row.addWidget(lbl)
            row.addWidget(spin)
            return row

        # X
        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-20.0, 20.0)
        self.spin_x.setSingleStep(0.1)
        self.spin_x.setDecimals(3)
        self.spin_x.setFixedHeight(20)
        self.spin_x.setStyleSheet(spin_style)
        self.spin_x.valueChanged.connect(self._on_xyz_changed)
        cl.addLayout(_row("X  左/右:", self.spin_x))

        # Z front/back → internal pos[1]
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-20.0, 20.0)
        self.spin_z.setSingleStep(0.1)
        self.spin_z.setDecimals(3)
        self.spin_z.setFixedHeight(20)
        self.spin_z.setStyleSheet(spin_style)
        self.spin_z.valueChanged.connect(self._on_xyz_changed)
        cl.addLayout(_row("Z  前/后:", self.spin_z))

        # Y height → internal pos[2]
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-10.0, 10.0)
        self.spin_y.setSingleStep(0.1)
        self.spin_y.setDecimals(3)
        self.spin_y.setFixedHeight(20)
        self.spin_y.setStyleSheet(spin_style)
        self.spin_y.valueChanged.connect(self._on_xyz_changed)
        cl.addLayout(_row("Y  高度:", self.spin_y))

        # Distance
        self.spin_dist = QDoubleSpinBox()
        self.spin_dist.setRange(0.0, 30.0)
        self.spin_dist.setSingleStep(0.1)
        self.spin_dist.setDecimals(3)
        self.spin_dist.setFixedHeight(20)
        self.spin_dist.setStyleSheet(spin_style)
        self.spin_dist.valueChanged.connect(self._on_polar_changed)
        cl.addLayout(_row("距离:", self.spin_dist))

        # Angle
        self.spin_angle = QDoubleSpinBox()
        self.spin_angle.setRange(-180.0, 180.0)
        self.spin_angle.setSingleStep(1.0)
        self.spin_angle.setDecimals(1)
        self.spin_angle.setSuffix("°")
        self.spin_angle.setWrapping(True)
        self.spin_angle.setFixedHeight(20)
        self.spin_angle.setStyleSheet(spin_style)
        self.spin_angle.valueChanged.connect(self._on_polar_changed)
        cl.addLayout(_row("方位角:", self.spin_angle))

        self.coord_widget.setVisible(False)
        layout.addWidget(self.coord_widget)

    # ── Expand toggle ─────────────────────────────────────────────

    def _on_expand(self, checked: bool):
        self.btn_expand.setText(("▼" if checked else "▶") + "  坐标精确控制")
        self.coord_widget.setVisible(checked)

    # ── Rec toggle ────────────────────────────────────────────────

    def _on_rec_toggled(self, active: bool):
        self.pad.set_recording(active)
        self.rec_toggled.emit(self.track_id, active)

    # ── SpatialPad drag → coord_changed ──────────────────────────

    def _on_pad_position(self, ix: float, iy: float, iz: float):
        """Forward SpatialPad drag to the main coord pipeline."""
        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)
        # iz unchanged (pad is XZ only)
        dist = math.sqrt(ix * ix + iy * iy + iz * iz)
        angle = math.degrees(math.atan2(ix, iy)) if (abs(ix) > 1e-9 or abs(iy) > 1e-9) else 0.0
        self.spin_dist.setValue(dist)
        self.spin_angle.setValue(angle)
        self._updating = False
        self.coord_changed.emit(self.track_id, ix, iy, self.spin_y.value())

    # ── Spinbox change handlers ───────────────────────────────────

    def _on_xyz_changed(self):
        if self._updating:
            return
        ix = self.spin_x.value()
        iy = self.spin_z.value()   # user Z → internal Y
        iz = self.spin_y.value()   # user Y → internal Z

        self._updating = True
        dist = math.sqrt(ix * ix + iy * iy + iz * iz)
        angle = math.degrees(math.atan2(ix, iy)) if (abs(ix) > 1e-9 or abs(iy) > 1e-9) else 0.0
        self.spin_dist.setValue(dist)
        self.spin_angle.setValue(angle)
        self.pad.set_position(ix, iy, iz)
        self._updating = False

        self.coord_changed.emit(self.track_id, ix, iy, iz)

    def _on_polar_changed(self):
        if self._updating:
            return
        dist = self.spin_dist.value()
        angle_rad = math.radians(self.spin_angle.value())
        ix = dist * math.sin(angle_rad)
        iy = dist * math.cos(angle_rad)
        iz = self.spin_y.value()

        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)
        self.pad.set_position(ix, iy, iz)
        self._updating = False

        self.coord_changed.emit(self.track_id, ix, iy, iz)

    # ── Public API ────────────────────────────────────────────────

    def set_position(self, ix: float, iy: float, iz: float):
        """Update all position displays without emitting coord_changed."""
        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)
        self.spin_y.setValue(iz)
        dist = math.sqrt(ix * ix + iy * iy + iz * iz)
        angle = math.degrees(math.atan2(ix, iy)) if (abs(ix) > 1e-9 or abs(iy) > 1e-9) else 0.0
        self.spin_dist.setValue(dist)
        self.spin_angle.setValue(angle)
        self.pad.set_position(ix, iy, iz)
        self._updating = False

    def set_trajectory(self, pts: np.ndarray | None, keyframes: list):
        """Update SpatialPad motion path and keyframe diamonds."""
        self.pad.set_trajectory(pts)
        self.pad.set_keyframe_positions(keyframes)

    def set_playing(self, active: bool):
        self.pad.set_playing(active)

    def is_rec_active(self) -> bool:
        return self.btn_rec.isChecked()

    def stop_recording(self):
        """Programmatically deactivate REC (triggers rec_toggled signal)."""
        if self.btn_rec.isChecked():
            self.btn_rec.setChecked(False)

    # ── Style helper ──────────────────────────────────────────────

    @staticmethod
    def _toggle_style(active_color: str) -> str:
        return f"""
            QPushButton {{ background:{BG_PANEL}; color:{TEXT_SECONDARY};
                           border:1px solid {BORDER_COLOR}; border-radius:2px;
                           font-size:9px; font-weight:bold; }}
            QPushButton:checked {{ background:{active_color}; color:#000; }}
        """


class TrackPanel(QWidget):
    """Left sidebar: one TrackItem per audio track."""

    solo_toggled       = pyqtSignal(int, bool)
    mute_toggled       = pyqtSignal(int, bool)
    priority_changed   = pyqtSignal(int, int)
    remove_clicked     = pyqtSignal(int)
    coord_changed      = pyqtSignal(int, float, float, float)
    keyframe_requested = pyqtSignal(int)
    rec_toggled        = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(300)
        self.setStyleSheet(f"background-color:{BG_PANEL};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        hdr = QLabel("TRACKS")
        hdr.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:11px; padding:4px;")
        hdr.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(hdr)

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
        if track_id in self._items:
            self._items[track_id].set_position(ix, iy, iz)

    def update_track_trajectory(self, track_id: int,
                                pts: np.ndarray | None, keyframes: list):
        """Refresh the SpatialPad motion path and keyframe diamonds."""
        if track_id in self._items:
            self._items[track_id].set_trajectory(pts, keyframes)

    def set_playing(self, active: bool):
        for item in self._items.values():
            item.set_playing(active)

    def get_rec_tracks(self) -> set[int]:
        return {tid for tid, item in self._items.items() if item.is_rec_active()}

    def stop_all_recording(self):
        for item in self._items.values():
            item.stop_recording()
