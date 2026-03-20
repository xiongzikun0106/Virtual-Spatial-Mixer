"""
SpatialPad – 2D bird's-eye XZ positioning pad with AE-style motion path display.

Internal coordinate convention (matches the rest of the codebase):
    ix  = pos[0]  X  left(−) / right(+)   → pad horizontal
    iy  = pos[1]  internal Y = user Z front(+) / back(−)  → pad vertical (up = front)
    iz  = pos[2]  internal Z = user Y height               → shown as numeric label

User interaction:
    • Click / drag           → set position immediately (emits position_changed)
    • While REC + playing    → app records the stream of position_changed events
    • Trajectory curve       → drawn from keyframe spline points supplied by app
    • Keyframe diamonds      → drawn at each keyframe time's XZ position
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QSizePolicy, QToolTip
from PyQt6.QtCore import pyqtSignal, Qt, QPointF, QRectF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QPolygonF,
)

from src.ui.theme import MONO_FONT


class SpatialPad(QWidget):
    """Interactive 2D positioning pad (XZ plane, top-down view).

    Signals
    -------
    position_changed(ix, iy, iz)
        Emitted whenever the user clicks or drags inside the pad.
    """

    position_changed = pyqtSignal(float, float, float)

    _RANGE = 20.0          # world units shown from centre to edge (±RANGE)
    _DOT_R = 7             # source dot radius in pixels
    _KF_HALF = 5           # keyframe diamond half-size in pixels

    def __init__(self, track_id: int, color: tuple[int, int, int], parent=None):
        super().__init__(parent)
        self.track_id = track_id
        self._color = color         # (r, g, b)

        # Current position (internal coordinates)
        self._ix: float = 0.0
        self._iy: float = 0.0
        self._iz: float = 0.0

        # State flags
        self._recording: bool = False
        self._dragging: bool = False
        self._is_playing: bool = False

        # Trajectory curve points: Nx3 array (ix, iy, iz) from spline
        self._traj: np.ndarray | None = None
        # Keyframe marker positions: list of (ix, iy) tuples for diamonds
        self._kf_positions: list[tuple[float, float]] = []

        self.setMinimumSize(170, 150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setToolTip("")

    # ── Public API ────────────────────────────────────────────────

    def set_position(self, ix: float, iy: float, iz: float):
        """Update displayed position without emitting signals."""
        self._ix, self._iy, self._iz = ix, iy, iz
        self.update()

    def set_recording(self, active: bool):
        """Toggle the visual recording indicator."""
        self._recording = active
        self.update()

    def set_playing(self, active: bool):
        self._is_playing = active

    def set_trajectory(self, pts: np.ndarray | None):
        """Supply Nx3 spline points for the motion path curve."""
        self._traj = pts
        self.update()

    def set_keyframe_positions(self, keyframes: list):
        """Supply list of (t, ix, iy, iz) keyframe tuples for diamond markers."""
        self._kf_positions = [(kf[1], kf[2]) for kf in keyframes]
        self.update()

    # ── Geometry helpers ──────────────────────────────────────────

    def _content_rect(self) -> QRectF:
        m = 18
        return QRectF(m, m, self.width() - 2 * m, self.height() - 2 * m)

    def _w2p(self, wx: float, wy: float) -> QPointF:
        """World (ix, iy) → pad pixel coordinates."""
        r = self._content_rect()
        px = r.x() + (wx / self._RANGE * 0.5 + 0.5) * r.width()
        py = r.y() + (0.5 - wy / self._RANGE * 0.5) * r.height()
        return QPointF(px, py)

    def _p2w(self, px: float, py: float) -> tuple[float, float]:
        """Pad pixel → world (ix, iy), clamped to ±RANGE."""
        r = self._content_rect()
        wx = ((px - r.x()) / r.width() - 0.5) * 2.0 * self._RANGE
        wy = (0.5 - (py - r.y()) / r.height()) * 2.0 * self._RANGE
        return (
            float(np.clip(wx, -self._RANGE, self._RANGE)),
            float(np.clip(wy, -self._RANGE, self._RANGE)),
        )

    # ── Paint ─────────────────────────────────────────────────────

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        r, g, b = self._color

        # Widget background
        p.fillRect(0, 0, w, h, QColor("#141414"))

        cr = self._content_rect()
        p.fillRect(cr.toRect(), QColor("#1A1A1A"))

        # ── Grid lines every 5 world units ──
        p.setPen(QPen(QColor("#252525"), 1))
        for v in np.arange(-self._RANGE, self._RANGE + 0.1, 5.0):
            p.drawLine(self._w2p(v, -self._RANGE), self._w2p(v, self._RANGE))
            p.drawLine(self._w2p(-self._RANGE, v), self._w2p(self._RANGE, v))

        # ── Axes (slightly brighter) ──
        p.setPen(QPen(QColor("#323232"), 1))
        p.drawLine(self._w2p(0, -self._RANGE), self._w2p(0, self._RANGE))
        p.drawLine(self._w2p(-self._RANGE, 0), self._w2p(self._RANGE, 0))

        # ── Axis labels ──
        font_s = QFont(MONO_FONT, 7)
        p.setFont(font_s)
        p.setPen(QColor("#505050"))
        _tp = self._w2p(0, self._RANGE)
        p.drawText(int(_tp.x()) + 2, int(_tp.y()) + 10, "+Z 前")
        _bt = self._w2p(0, -self._RANGE)
        p.drawText(int(_bt.x()) + 2, int(_bt.y()) - 3, "-Z 后")
        _lt = self._w2p(-self._RANGE, 0)
        p.drawText(int(_lt.x()) + 1, int(_lt.y()) - 2, "-X")
        _rt = self._w2p(self._RANGE, 0)
        p.drawText(int(_rt.x()) - 15, int(_rt.y()) - 2, "+X")

        # ── Listener origin marker ──
        ori = self._w2p(0, 0)
        p.setPen(QPen(QColor("#FFFFFF55"), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ori, 5, 5)
        p.drawLine(QPointF(ori.x() - 4, ori.y()), QPointF(ori.x() + 4, ori.y()))
        p.drawLine(QPointF(ori.x(), ori.y() - 4), QPointF(ori.x(), ori.y() + 4))

        # ── Trajectory curve ──
        if self._traj is not None and len(self._traj) >= 2:
            traj_color = QColor(r, g, b, 100)
            p.setPen(QPen(traj_color, 1.5))
            for i in range(len(self._traj) - 1):
                p1 = self._w2p(self._traj[i][0], self._traj[i][1])
                p2 = self._w2p(self._traj[i + 1][0], self._traj[i + 1][1])
                p.drawLine(p1, p2)

        # ── Keyframe diamonds ──
        h_s = self._KF_HALF
        for kx, ky in self._kf_positions:
            c = self._w2p(kx, ky)
            diamond = QPolygonF([
                QPointF(c.x(), c.y() - h_s),
                QPointF(c.x() + h_s, c.y()),
                QPointF(c.x(), c.y() + h_s),
                QPointF(c.x() - h_s, c.y()),
            ])
            p.setPen(QPen(QColor(255, 255, 255, 180), 1))
            p.setBrush(QBrush(QColor(r, g, b, 200)))
            p.drawPolygon(diamond)

        # ── Source position dot ──
        dot = self._w2p(self._ix, self._iy)

        # Glow ring when recording
        if self._recording:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor(r, g, b, 35)))
            p.drawEllipse(dot, 20, 20)
            p.setBrush(QBrush(QColor(r, g, b, 55)))
            p.drawEllipse(dot, 13, 13)

        p.setPen(QPen(QColor(255, 255, 255, 210), 1.5))
        p.setBrush(QBrush(QColor(r, g, b, 230)))
        p.drawEllipse(dot, self._DOT_R, self._DOT_R)

        # Inner highlight
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(QColor(255, 255, 255, 90)))
        p.drawEllipse(QPointF(dot.x() - 2, dot.y() - 2), 2, 2)

        # ── Position readout ──
        p.setFont(font_s)
        p.setPen(QColor("#777777"))
        p.drawText(3, h - 3, f"X{self._ix:+.1f}  Z{self._iy:+.1f}  Y高{self._iz:+.1f}")

        # ── REC indicator badge ──
        if self._recording:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(QColor("#FF1744")))
            p.drawEllipse(w - 12, 4, 8, 8)
            p.setPen(QColor("#FF1744"))
            p.setFont(QFont(MONO_FONT, 6))
            p.drawText(w - 28, 12, "REC")

        # ── Border ──
        border_col = "#FF1744" if self._recording else "#2C2C2C"
        p.setPen(QPen(QColor(border_col), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(cr)

        p.end()

    # ── Mouse interaction ─────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._emit_from(event.position())

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._dragging:
            self._emit_from(event.position())
        else:
            # Hover: show tooltip with nearest keyframe info if within distance
            self._update_hover_tooltip(event.position())

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False

    def _emit_from(self, qpos: QPointF):
        wx, wy = self._p2w(qpos.x(), qpos.y())
        self._ix = wx
        self._iy = wy
        self.update()
        self.position_changed.emit(wx, wy, self._iz)

    def _update_hover_tooltip(self, qpos: QPointF):
        """Show keyframe position tooltip on hover."""
        if not self._kf_positions:
            return
        px, py = qpos.x(), qpos.y()
        for kx, ky in self._kf_positions:
            c = self._w2p(kx, ky)
            if abs(px - c.x()) < 10 and abs(py - c.y()) < 10:
                QToolTip.showText(
                    self.mapToGlobal(qpos.toPoint()),
                    f"X{kx:+.2f}  Z{ky:+.2f}",
                    self,
                )
                return
        QToolTip.hideText()
