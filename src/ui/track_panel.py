"""
Track Panel – left sidebar with per-track controls.

Each TrackItem contains:
  • Top row    : colour dot · name · remove (✕)
  • Control row: S (solo) · M (mute) · ● REC · +KF · priority
  • Position   : X / Z / Y spinboxes (always visible, sole position-control entry)

The 2D SpatialPad has been fully removed.
Position is now edited exclusively through the X/Z/Y spinboxes here,
or by dragging spheres in the 3D viewport.
"""

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
    """Per-track control strip with position spinboxes."""

    solo_toggled       = pyqtSignal(int, bool)
    mute_toggled       = pyqtSignal(int, bool)
    priority_changed   = pyqtSignal(int, int)
    remove_clicked     = pyqtSignal(int)
    coord_changed      = pyqtSignal(int, float, float, float)  # tid, ix, iy, iz
    keyframe_requested = pyqtSignal(int)
    rec_toggled        = pyqtSignal(int, bool)

    def __init__(self, track_id: int, name: str,
                 color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self._color = color
        self._updating = False
        self._rec_active = False

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._update_frame_style(recording=False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 5, 6, 5)
        layout.setSpacing(3)

        # ── Top row: dot · name · remove ────────────────────────
        top = QHBoxLayout()
        top.setSpacing(5)
        r, g, b = color
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(
            f"background-color:rgb({r},{g},{b}); border-radius:5px;"
        )
        top.addWidget(dot)

        name_lbl = QLabel(name)
        name_lbl.setStyleSheet(
            f"color:{TEXT_PRIMARY}; font-size:11px; font-weight:bold;"
        )
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

        # ── Control row: S · M · REC · +KF · P ──────────────────
        ctrl = QHBoxLayout()
        ctrl.setSpacing(3)

        self.btn_solo = QPushButton("S")
        self.btn_solo.setCheckable(True)
        self.btn_solo.setFixedSize(22, 18)
        self.btn_solo.setStyleSheet(self._toggle_style("#FFD600"))
        self.btn_solo.toggled.connect(
            lambda v: self.solo_toggled.emit(self.track_id, v)
        )

        self.btn_mute = QPushButton("M")
        self.btn_mute.setCheckable(True)
        self.btn_mute.setFixedSize(22, 18)
        self.btn_mute.setStyleSheet(self._toggle_style("#FF1744"))
        self.btn_mute.toggled.connect(
            lambda v: self.mute_toggled.emit(self.track_id, v)
        )

        self.btn_rec = QPushButton("● REC")
        self.btn_rec.setCheckable(True)
        self.btn_rec.setFixedHeight(18)
        self.btn_rec.setStyleSheet(self._toggle_style("#FF1744"))
        self.btn_rec.setToolTip("勾选后按住 R 键开始录制")
        self.btn_rec.toggled.connect(self._on_rec_toggled)

        self.btn_kf = QPushButton("+KF")
        self.btn_kf.setFixedHeight(18)
        self.btn_kf.setToolTip("在当前时刻添加关键帧")
        self.btn_kf.setStyleSheet(f"""
            QPushButton {{ background:{BG_PANEL}; color:{TEXT_SECONDARY};
                           border:1px solid {BORDER_COLOR}; border-radius:2px;
                           font-size:9px; font-weight:bold; }}
            QPushButton:hover  {{ background:{ACCENT}; color:#000; }}
            QPushButton:pressed {{ background:#00B8D4; color:#000; }}
        """)
        self.btn_kf.clicked.connect(
            lambda: self.keyframe_requested.emit(self.track_id)
        )

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

        # ── Position display (always visible) ───────────────────
        layout.addWidget(self._build_position_widget())

    # ── Position widget ───────────────────────────────────────────

    def _build_position_widget(self) -> QWidget:
        container = QWidget()
        cl = QHBoxLayout(container)
        cl.setContentsMargins(0, 2, 0, 0)
        cl.setSpacing(4)

        spin_style = f"""
            QDoubleSpinBox {{
                background:{BG_PANEL}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_COLOR}; font-size:9px; padding:1px;
            }}
            QDoubleSpinBox:focus {{ border-color:{ACCENT}; }}
        """

        def _labeled(label_text: str, spin: QDoubleSpinBox) -> QHBoxLayout:
            row = QHBoxLayout()
            row.setSpacing(2)
            lbl = QLabel(label_text)
            lbl.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:8px;")
            lbl.setFixedWidth(14)
            row.addWidget(lbl)
            row.addWidget(spin)
            return row

        self.spin_x = QDoubleSpinBox()
        self.spin_x.setRange(-20.0, 20.0)
        self.spin_x.setSingleStep(0.1)
        self.spin_x.setDecimals(2)
        self.spin_x.setFixedHeight(18)
        self.spin_x.setStyleSheet(spin_style)
        self.spin_x.setToolTip("X — 左(−) / 右(+)")
        self.spin_x.valueChanged.connect(self._on_spin_changed)

        # Z front/back → internal pos[1]
        self.spin_z = QDoubleSpinBox()
        self.spin_z.setRange(-20.0, 20.0)
        self.spin_z.setSingleStep(0.1)
        self.spin_z.setDecimals(2)
        self.spin_z.setFixedHeight(18)
        self.spin_z.setStyleSheet(spin_style)
        self.spin_z.setToolTip("Z — 后(−) / 前(+)")
        self.spin_z.valueChanged.connect(self._on_spin_changed)

        # Y height → internal pos[2]
        self.spin_y = QDoubleSpinBox()
        self.spin_y.setRange(-10.0, 10.0)
        self.spin_y.setSingleStep(0.1)
        self.spin_y.setDecimals(2)
        self.spin_y.setFixedHeight(18)
        self.spin_y.setStyleSheet(spin_style)
        self.spin_y.setToolTip("Y — 高度")
        self.spin_y.valueChanged.connect(self._on_spin_changed)

        cl.addLayout(_labeled("X", self.spin_x))
        cl.addLayout(_labeled("Z", self.spin_z))
        cl.addLayout(_labeled("Y", self.spin_y))
        return container

    # ── Event handlers ────────────────────────────────────────────

    def _on_rec_toggled(self, active: bool):
        self._rec_active = active
        self._update_frame_style(active)
        self.rec_toggled.emit(self.track_id, active)

    def _on_spin_changed(self):
        if self._updating:
            return
        ix = self.spin_x.value()
        iy = self.spin_z.value()   # user Z → internal Y
        iz = self.spin_y.value()   # user Y → internal Z
        self.coord_changed.emit(self.track_id, ix, iy, iz)

    # ── Public API ────────────────────────────────────────────────

    def set_position(self, ix: float, iy: float, iz: float):
        """Update displayed position without emitting coord_changed."""
        self._updating = True
        self.spin_x.setValue(ix)
        self.spin_z.setValue(iy)
        self.spin_y.setValue(iz)
        self._updating = False

    def set_playing(self, _active: bool):
        pass  # no-op (SpatialPad removed)

    def set_rec_highlight(self, active: bool):
        """Visual indicator when R-key global recording is active and this track is in REC mode."""
        self._update_frame_style(active and self._rec_active)

    def is_rec_active(self) -> bool:
        return self.btn_rec.isChecked()

    def stop_recording(self):
        """Programmatically deactivate REC button (triggers rec_toggled signal)."""
        if self.btn_rec.isChecked():
            self.btn_rec.setChecked(False)

    # ── Style helpers ─────────────────────────────────────────────

    def _update_frame_style(self, recording: bool):
        border_col = "#FF1744" if recording else BORDER_COLOR
        self.setStyleSheet(f"""
            TrackItem {{
                background-color: {BG_LIGHTER};
                border: 1px solid {border_col};
                border-radius: 4px;
            }}
        """)

    @staticmethod
    def _toggle_style(active_color: str) -> str:
        return f"""
            QPushButton {{
                background:{BG_PANEL}; color:{TEXT_SECONDARY};
                border:1px solid {BORDER_COLOR}; border-radius:2px;
                font-size:9px; font-weight:bold;
            }}
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
        self.setFixedWidth(290)
        self.setStyleSheet(f"background-color:{BG_PANEL};")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(0)

        # Header with REC indicator
        hdr_row = QHBoxLayout()
        hdr_lbl = QLabel("TRACKS")
        hdr_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:11px; padding:4px;"
        )
        hdr_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hdr_row.addWidget(hdr_lbl, 1)

        self._rec_indicator = QLabel("● 录制中")
        self._rec_indicator.setStyleSheet(
            "color: #FF1744; font-size: 10px; font-weight: bold; padding: 4px;"
        )
        self._rec_indicator.setVisible(False)
        hdr_row.addWidget(self._rec_indicator)
        outer.addLayout(hdr_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { border: none; }")

        self._container = QWidget()
        self._layout    = QVBoxLayout(self._container)
        self._layout.setContentsMargins(2, 2, 2, 2)
        self._layout.setSpacing(4)
        self._layout.addStretch()

        scroll.setWidget(self._container)
        outer.addWidget(scroll)

        self._items: dict[int, TrackItem] = {}

    # ── Track management ──────────────────────────────────────────

    def add_track(self, track_id: int, name: str,
                  color: tuple[int, int, int]):
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

    # ── Public API ────────────────────────────────────────────────

    def set_track_position(self, track_id: int,
                           ix: float, iy: float, iz: float):
        if track_id in self._items:
            self._items[track_id].set_position(ix, iy, iz)

    def update_track_trajectory(self, track_id: int, pts, keyframes: list):
        """No-op: SpatialPad removed; trajectory shown only in 3D viewport."""

    def set_playing(self, active: bool):
        for item in self._items.values():
            item.set_playing(active)

    def set_global_rec_active(self, active: bool):
        """Show/hide the global recording indicator and highlight REC tracks."""
        self._rec_indicator.setVisible(active)
        for item in self._items.values():
            item.set_rec_highlight(active)

    def get_rec_tracks(self) -> set[int]:
        return {tid for tid, item in self._items.items() if item.is_rec_active()}

    def stop_all_recording(self):
        for item in self._items.values():
            item.stop_recording()
