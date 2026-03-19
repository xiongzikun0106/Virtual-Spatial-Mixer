import numpy as np
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QFont, QPen, QBrush, QMouseEvent, QPolygonF

from src.ui.theme import (
    BG_PANEL, BG_LIGHTER, GRID_COLOR, TEXT_PRIMARY, TEXT_SECONDARY,
    PLAYHEAD_COLOR, MONO_FONT, BORDER_COLOR, ACCENT,
)

RULER_HEIGHT = 24
TRACK_ROW_HEIGHT = 50
KEYFRAME_RADIUS = 5


class TimelineWidget(QWidget):
    """Custom-painted timeline showing waveform overviews, keyframes, and playhead."""

    seek_requested = pyqtSignal(float)  # time in seconds
    keyframe_added = pyqtSignal(int, float)  # track_id, time_sec
    keyframe_moved = pyqtSignal(int, int, float)  # track_id, kf_index, new_time

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setFixedHeight(150)
        self.setStyleSheet(f"background-color: {BG_PANEL};")

        self._tracks: list[dict] = []
        self._duration = 10.0
        self._playhead_time = 0.0
        self._pixels_per_second = 60.0
        self._scroll_offset = 0.0

        self._dragging_playhead = False
        self._dragging_kf = None  # (track_idx, kf_idx)

        self.setMouseTracking(True)

    def set_tracks(self, tracks: list[dict]):
        """tracks: [{"id": int, "name": str, "color": (r,g,b),
                     "waveform": np.ndarray, "keyframes": [(t,x,y,z), ...]}]"""
        self._tracks = tracks
        self.update()

    def set_duration(self, dur: float):
        self._duration = max(1.0, dur)
        self.update()

    def set_playhead(self, time_sec: float):
        self._playhead_time = time_sec
        self._ensure_playhead_visible()
        self.update()

    def _ensure_playhead_visible(self):
        x = self._time_to_x(self._playhead_time)
        visible_left = 60
        visible_right = self.width() - 20
        if x > visible_right:
            self._scroll_offset += (x - visible_right + 50)
        elif x < visible_left and self._scroll_offset > 0:
            target = self._playhead_time * self._pixels_per_second - 50
            self._scroll_offset = max(0.0, target)

    def _time_to_x(self, t: float) -> float:
        return (t * self._pixels_per_second) - self._scroll_offset + 60

    def _x_to_time(self, x: float) -> float:
        return (x - 60 + self._scroll_offset) / self._pixels_per_second

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        painter.fillRect(0, 0, w, h, QColor(BG_PANEL))

        painter.fillRect(0, 0, 60, h, QColor(BG_LIGHTER))

        self._draw_ruler(painter, w)
        self._draw_tracks(painter, w, h)
        self._draw_playhead(painter, h)

        painter.end()

    def _draw_ruler(self, painter: QPainter, width: int):
        painter.setPen(QPen(QColor(TEXT_SECONDARY), 1))
        font = QFont(MONO_FONT, 8)
        painter.setFont(font)

        t = 0.0
        step = self._nice_step()
        while t <= self._duration + step:
            x = self._time_to_x(t)
            if 60 <= x <= width:
                painter.drawLine(int(x), 0, int(x), RULER_HEIGHT)
                mins = int(t) // 60
                secs = t - mins * 60
                painter.drawText(int(x) + 2, RULER_HEIGHT - 4, f"{mins}:{secs:04.1f}")
            t += step

    def _nice_step(self) -> float:
        pps = self._pixels_per_second
        if pps > 100:
            return 0.5
        if pps > 40:
            return 1.0
        if pps > 15:
            return 5.0
        return 10.0

    def _draw_tracks(self, painter: QPainter, width: int, height: int):
        y_offset = RULER_HEIGHT
        font = QFont(MONO_FONT, 9)
        painter.setFont(font)

        for i, track in enumerate(self._tracks):
            y = y_offset + i * TRACK_ROW_HEIGHT
            if y > height:
                break

            painter.setPen(QPen(QColor(BORDER_COLOR), 1))
            painter.drawLine(0, y, width, y)

            r, g, b = track["color"]
            painter.setPen(QPen(QColor(TEXT_PRIMARY), 1))
            painter.drawText(4, y + TRACK_ROW_HEIGHT // 2 + 4, track["name"][:8])

            waveform = track.get("waveform")
            if waveform is not None and len(waveform) > 0:
                self._draw_waveform(painter, waveform, track["color"],
                                    60, y + 4, width - 60, TRACK_ROW_HEIGHT - 8,
                                    track.get("track_duration", self._duration))

            keyframes = track.get("keyframes", [])
            for ki, kf in enumerate(keyframes):
                kf_time = kf[0]
                kx = self._time_to_x(kf_time)
                ky = y + TRACK_ROW_HEIGHT // 2
                if 60 <= kx <= width:
                    painter.setPen(QPen(QColor(r, g, b), 1))
                    painter.setBrush(QBrush(QColor(r, g, b)))
                    painter.drawEllipse(QPointF(kx, ky), KEYFRAME_RADIUS, KEYFRAME_RADIUS)

        bottom_line_y = y_offset + len(self._tracks) * TRACK_ROW_HEIGHT
        if bottom_line_y < height:
            painter.setPen(QPen(QColor(BORDER_COLOR), 1))
            painter.drawLine(0, bottom_line_y, width, bottom_line_y)

    def _draw_waveform(self, painter: QPainter, waveform: np.ndarray, color: tuple,
                       x0: int, y0: int, w: int, h: int, duration: float):
        r, g, b = color
        painter.setPen(QPen(QColor(r, g, b, 80), 1))

        n = len(waveform)
        mid_y = y0 + h / 2
        half_h = h / 2

        for i in range(min(n, w)):
            t = (i / w) * duration
            px = self._time_to_x(t)
            if px < x0 or px > x0 + w:
                continue
            idx = int(i / w * n)
            idx = min(idx, n - 1)
            amp = waveform[idx] * half_h
            painter.drawLine(int(px), int(mid_y - amp), int(px), int(mid_y + amp))

    def _draw_playhead(self, painter: QPainter, height: int):
        x = self._time_to_x(self._playhead_time)
        painter.setPen(QPen(QColor(PLAYHEAD_COLOR), 2))
        painter.drawLine(int(x), 0, int(x), height)

        painter.setBrush(QBrush(QColor(PLAYHEAD_COLOR)))
        triangle = QPolygonF([
            QPointF(x - 5, 0),
            QPointF(x + 5, 0),
            QPointF(x, 8),
        ])
        painter.drawPolygon(triangle)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            px = self._time_to_x(self._playhead_time)
            if abs(pos.x() - px) < 8:
                self._dragging_playhead = True
                return

            kf_hit = self._hit_keyframe(pos.x(), pos.y())
            if kf_hit is not None:
                self._dragging_kf = kf_hit
                return

            if pos.y() < RULER_HEIGHT:
                t = self._x_to_time(pos.x())
                t = max(0.0, min(t, self._duration))
                self.seek_requested.emit(t)
                self._dragging_playhead = True

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            track_idx = self._y_to_track(pos.y())
            if track_idx is not None and track_idx < len(self._tracks):
                t = self._x_to_time(pos.x())
                t = max(0.0, min(t, self._duration))
                self.keyframe_added.emit(self._tracks[track_idx]["id"], t)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()
        if self._dragging_playhead:
            t = self._x_to_time(pos.x())
            t = max(0.0, min(t, self._duration))
            self.seek_requested.emit(t)
        elif self._dragging_kf is not None:
            ti, ki = self._dragging_kf
            t = self._x_to_time(pos.x())
            t = max(0.0, min(t, self._duration))
            if ti < len(self._tracks):
                self.keyframe_moved.emit(self._tracks[ti]["id"], ki, t)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging_playhead = False
        self._dragging_kf = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._pixels_per_second = max(5.0, min(300.0, self._pixels_per_second * factor))
        else:
            self._scroll_offset -= delta * 0.5
            self._scroll_offset = max(0, self._scroll_offset)
        self.update()

    def _y_to_track(self, y: float) -> int | None:
        idx = int((y - RULER_HEIGHT) / TRACK_ROW_HEIGHT)
        if idx < 0 or idx >= len(self._tracks):
            return None
        return idx

    def _hit_keyframe(self, mx: float, my: float) -> tuple[int, int] | None:
        for ti, track in enumerate(self._tracks):
            y_center = RULER_HEIGHT + ti * TRACK_ROW_HEIGHT + TRACK_ROW_HEIGHT // 2
            if abs(my - y_center) > KEYFRAME_RADIUS + 4:
                continue
            for ki, kf in enumerate(track.get("keyframes", [])):
                kx = self._time_to_x(kf[0])
                if abs(mx - kx) < KEYFRAME_RADIUS + 4:
                    return (ti, ki)
        return None
