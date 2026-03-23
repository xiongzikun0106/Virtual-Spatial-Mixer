"""
Timeline widget – AE-style keyframe editing with segment motion indicators.

Layout
------
  ┌─────────────────────────────────────────────────────┐
  │  [ruler with time marks]                            │
  ├──────┬──────────────────────────────────────────────┤
  │ name │ waveform … ──◇──[seg]──◇──  keyframes+segs  │  ← per track row
  └──────┴──────────────────────────────────────────────┘

Interactions
------------
  • Left-click ruler / drag playhead  → seek
  • Left-click keyframe diamond       → seek + select
  • Left-drag keyframe diamond        → move keyframe in time
  • Left-click segment line           → interval_clicked signal
  • Double-click track row            → add keyframe
  • Right-click keyframe              → context menu (Delete / Clear all)
  • Ctrl + scroll                     → zoom time axis
  • Scroll                            → horizontal scroll

Signals
-------
  seek_requested(float)
  keyframe_added(int, float)
  keyframe_moved(int, int, float)
  keyframe_deleted(int, int)
  keyframes_cleared(int)
  keyframe_selected(int, int)
  interval_clicked(int, int)          track_id, segment_index
"""

import numpy as np
from PyQt6.QtWidgets import QWidget, QMenu, QToolTip
from PyQt6.QtCore    import pyqtSignal, Qt, QPointF
from PyQt6.QtGui     import (
    QPainter, QColor, QFont, QPen, QBrush,
    QMouseEvent, QPolygonF, QAction,
)

from src.ui.theme import (
    BG_PANEL, BG_LIGHTER, BORDER_COLOR, TEXT_PRIMARY, TEXT_SECONDARY,
    PLAYHEAD_COLOR, MONO_FONT, ACCENT,
)
from src.core.trajectory import MotionType, MOTION_COLORS

RULER_H  = 26
ROW_H    = 52
KF_HALF  = 6
LABEL_W  = 64
SEG_Y_OFF = 6    # y-offset from row centre for the segment line


class TimelineWidget(QWidget):
    """AE-style timeline with waveforms, keyframe diamonds, segment lines, and playhead."""

    seek_requested    = pyqtSignal(float)
    keyframe_added    = pyqtSignal(int, float)
    keyframe_moved    = pyqtSignal(int, int, float)
    keyframe_deleted  = pyqtSignal(int, int)
    keyframes_cleared = pyqtSignal(int)
    keyframe_selected = pyqtSignal(int, int)
    interval_clicked  = pyqtSignal(int, int)   # track_id, segment_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(120)
        self.setFixedHeight(160)
        self.setStyleSheet(f"background-color: {BG_PANEL};")
        self.setMouseTracking(True)

        self._tracks: list[dict]  = []
        self._duration: float     = 10.0
        self._playhead_time: float = 0.0
        self._pixels_per_sec: float = 60.0
        self._scroll_x: float     = 0.0

        self._drag_playhead: bool             = False
        self._drag_kf: tuple[int, int] | None = None
        self._selected_kf: tuple[int, int] | None = None

    # ── Data API ──────────────────────────────────────────────────

    def set_tracks(self, tracks: list[dict]):
        """
        Each dict must have:
          id, name, color (r,g,b), waveform (np.ndarray),
          keyframes [(t,x,y,z)], segments [{"motion_type": str}],
          track_duration (float)
        """
        self._tracks = tracks
        self.update()

    def set_duration(self, dur: float):
        self._duration = max(1.0, dur)
        self.update()

    def set_playhead(self, t: float):
        self._playhead_time = t
        self._auto_scroll()
        self.update()

    # ── Coordinate helpers ────────────────────────────────────────

    def _t2x(self, t: float) -> float:
        return t * self._pixels_per_sec - self._scroll_x + LABEL_W

    def _x2t(self, x: float) -> float:
        return (x - LABEL_W + self._scroll_x) / self._pixels_per_sec

    def _auto_scroll(self):
        x = self._t2x(self._playhead_time)
        right = self.width() - 20
        if x > right:
            self._scroll_x += x - right + 60
        elif x < LABEL_W and self._scroll_x > 0:
            self._scroll_x = max(0.0,
                                  self._playhead_time * self._pixels_per_sec - 60)

    # ── Paint ─────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.fillRect(0, 0, w, h, QColor(BG_PANEL))
        p.fillRect(0, 0, LABEL_W, h, QColor(BG_LIGHTER))

        self._paint_ruler(p, w)
        self._paint_tracks(p, w, h)
        self._paint_playhead(p, h)
        p.end()

    def _paint_ruler(self, p: QPainter, w: int):
        p.fillRect(0, 0, w, RULER_H, QColor("#1C1C1C"))
        p.setPen(QPen(QColor(BORDER_COLOR), 1))
        p.drawLine(0, RULER_H, w, RULER_H)

        p.setFont(QFont(MONO_FONT, 7))
        step = self._time_step()
        t = 0.0
        while t <= self._duration + step:
            x = int(self._t2x(t))
            if LABEL_W <= x <= w:
                p.setPen(QPen(QColor("#444444"), 1))
                p.drawLine(x, RULER_H - 8, x, RULER_H)
                m = int(t) // 60
                s = t - m * 60
                p.setPen(QColor(TEXT_SECONDARY))
                p.drawText(x + 2, RULER_H - 8, f"{m}:{s:04.1f}")
            t += step

    def _time_step(self) -> float:
        pps = self._pixels_per_sec
        if pps > 120: return 0.5
        if pps > 50:  return 1.0
        if pps > 20:  return 5.0
        return 10.0

    def _paint_tracks(self, p: QPainter, w: int, h: int):
        p.setFont(QFont(MONO_FONT, 8))

        for ti, track in enumerate(self._tracks):
            y = RULER_H + ti * ROW_H
            if y >= h:
                break

            r, g, b   = track["color"]
            track_color = QColor(r, g, b)
            kfs       = track.get("keyframes", [])
            segs      = track.get("segments", [])

            # Row separator
            p.setPen(QPen(QColor(BORDER_COLOR), 1))
            p.drawLine(0, y, w, y)

            # Label column
            p.fillRect(0, y, LABEL_W, ROW_H, QColor(BG_LIGHTER))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(track_color))
            p.drawEllipse(8, y + ROW_H // 2 - 4, 8, 8)
            p.setPen(QColor(TEXT_PRIMARY))
            p.setFont(QFont(MONO_FONT, 8))
            p.drawText(20, y + ROW_H // 2 + 4, track["name"][:7])

            # Waveform
            wf  = track.get("waveform")
            dur = track.get("track_duration", self._duration)
            if wf is not None and len(wf) > 0 and dur > 0:
                self._paint_waveform(p, wf, track["color"],
                                     LABEL_W, y + 4, w - LABEL_W, ROW_H - 8, dur)

            # Keyframe count badge
            if kfs:
                badge_x = LABEL_W - 2
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(QColor(r, g, b, 160)))
                p.drawRoundedRect(badge_x - 18, y + 3, 18, 11, 3, 3)
                p.setPen(QColor(0, 0, 0))
                p.setFont(QFont(MONO_FONT, 6))
                p.drawText(badge_x - 16, y + 12, str(len(kfs)))
                p.setFont(QFont(MONO_FONT, 8))

            cy = y + ROW_H // 2

            # Segment lines (drawn before diamonds so diamonds appear on top)
            self._paint_segments(p, kfs, segs, cy, w)

            # Keyframe diamonds
            for ki, kf in enumerate(kfs):
                kx = int(self._t2x(kf[0]))
                if kx < LABEL_W or kx > w:
                    continue
                is_sel = self._selected_kf == (ti, ki)
                self._paint_diamond(p, kx, cy, track_color, is_sel)

        # Bottom border
        bottom_y = RULER_H + len(self._tracks) * ROW_H
        if bottom_y < h:
            p.setPen(QPen(QColor(BORDER_COLOR), 1))
            p.drawLine(0, bottom_y, w, bottom_y)

    def _paint_segments(self, p: QPainter, kfs: list, segs: list,
                        cy: int, w: int):
        """Draw colored segment lines between adjacent keyframe diamonds."""
        for si in range(min(len(segs), len(kfs) - 1)):
            kf_a = kfs[si]
            kf_b = kfs[si + 1]
            x_a  = int(self._t2x(kf_a[0]))
            x_b  = int(self._t2x(kf_b[0]))
            if x_b < LABEL_W or x_a > w:
                continue

            x_a = max(x_a, LABEL_W)
            x_b = min(x_b, w)

            seg_info   = segs[si] if si < len(segs) else {}
            mt_str     = seg_info.get("motion_type", MotionType.LINEAR.value)
            try:
                mt = MotionType(mt_str)
            except ValueError:
                mt = MotionType.LINEAR

            color_hex  = MOTION_COLORS.get(mt, "#888888")
            line_color = QColor(color_hex)
            line_color.setAlpha(200)

            line_style = (Qt.PenStyle.DotLine if mt == MotionType.ORBIT
                          else Qt.PenStyle.SolidLine)

            p.setPen(QPen(line_color, 2, line_style))
            p.drawLine(x_a, cy + SEG_Y_OFF, x_b, cy + SEG_Y_OFF)

            # Motion type label in the middle of the segment
            mid_x = (x_a + x_b) // 2
            seg_w = x_b - x_a
            if seg_w > 30:
                p.setPen(line_color)
                p.setFont(QFont(MONO_FONT, 6))
                short = mt_str[:6]
                p.drawText(mid_x - 14, cy + SEG_Y_OFF - 2, short)
                p.setFont(QFont(MONO_FONT, 8))

    def _paint_diamond(self, p: QPainter, cx: int, cy: int,
                       color: QColor, selected: bool):
        hs  = KF_HALF
        pts = QPolygonF([
            QPointF(cx,      cy - hs),
            QPointF(cx + hs, cy),
            QPointF(cx,      cy + hs),
            QPointF(cx - hs, cy),
        ])
        if selected:
            p.setPen(QPen(QColor(255, 255, 255, 230), 1.5))
            p.setBrush(QBrush(QColor(255, 255, 255, 200)))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 160), 1))
            p.setBrush(QBrush(color))
        p.drawPolygon(pts)

    def _paint_waveform(self, p: QPainter, wf: np.ndarray,
                        color: tuple, x0: int, y0: int,
                        draw_w: int, h: int, dur: float):
        """
        Pixel-by-pixel waveform rendering.
        Correctly handles any scroll / zoom state and draws the full audio length.
        """
        r, g, b = color
        n   = len(wf)
        mid = y0 + h / 2
        half = h / 2

        # Determine which pixels to fill based on visible time range
        t_left  = self._x2t(x0)
        t_right = self._x2t(x0 + draw_w)

        # Clamp to audio content range
        sample_left  = max(0.0, t_left)
        sample_right = min(dur,  t_right)
        if sample_right <= sample_left:
            return

        px_start = max(x0, int(self._t2x(sample_left)))
        px_end   = min(x0 + draw_w, int(self._t2x(sample_right)) + 1)

        p.setPen(QPen(QColor(r, g, b, 70), 1))
        for px in range(px_start, px_end):
            t   = self._x2t(px)
            idx = int(t / dur * n)
            idx = max(0, min(idx, n - 1))
            amp = float(wf[idx]) * half
            p.drawLine(px, int(mid - amp), px, int(mid + amp))

    def _paint_playhead(self, p: QPainter, h: int):
        x = int(self._t2x(self._playhead_time))
        p.setPen(QPen(QColor(PLAYHEAD_COLOR), 2))
        p.drawLine(x, 0, x, h)
        p.setBrush(QBrush(QColor(PLAYHEAD_COLOR)))
        tri = QPolygonF([
            QPointF(x - 6, 0),
            QPointF(x + 6, 0),
            QPointF(x,     10),
        ])
        p.drawPolygon(tri)

    # ── Mouse events ──────────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent):
        pos = event.position()
        btn = event.button()

        if btn == Qt.MouseButton.LeftButton:
            # Playhead drag?
            ph_x = self._t2x(self._playhead_time)
            if abs(pos.x() - ph_x) < 8 and pos.y() < RULER_H + 10:
                self._drag_playhead = True
                return

            # Keyframe hit?
            hit = self._hit_kf(pos.x(), pos.y())
            if hit is not None:
                ti, ki = hit
                self._drag_kf    = hit
                self._selected_kf = hit
                kf_time = self._tracks[ti]["keyframes"][ki][0]
                self.seek_requested.emit(kf_time)
                self.keyframe_selected.emit(self._tracks[ti]["id"], ki)
                self.update()
                return

            # Ruler click → seek
            if pos.y() < RULER_H:
                t = max(0.0, min(self._x2t(pos.x()), self._duration))
                self.seek_requested.emit(t)
                self._drag_playhead = True
                return

            # Segment line hit?
            seg_hit = self._hit_segment(pos.x(), pos.y())
            if seg_hit is not None:
                ti, si = seg_hit
                self.interval_clicked.emit(self._tracks[ti]["id"], si)
                return

        elif btn == Qt.MouseButton.RightButton:
            hit = self._hit_kf(pos.x(), pos.y())
            if hit is not None:
                self._show_kf_menu(hit, event.globalPosition().toPoint())

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        pos = event.position()
        if event.button() == Qt.MouseButton.LeftButton:
            ti = self._y2track(pos.y())
            if ti is not None and ti < len(self._tracks):
                t = max(0.0, min(self._x2t(pos.x()), self._duration))
                self.keyframe_added.emit(self._tracks[ti]["id"], t)

    def mouseMoveEvent(self, event: QMouseEvent):
        pos = event.position()

        if self._drag_playhead:
            t = max(0.0, min(self._x2t(pos.x()), self._duration))
            self.seek_requested.emit(t)

        elif self._drag_kf is not None:
            ti, ki = self._drag_kf
            t = max(0.0, min(self._x2t(pos.x()), self._duration))
            if ti < len(self._tracks):
                self.keyframe_moved.emit(self._tracks[ti]["id"], ki, t)

        else:
            # Hover tooltip
            hit = self._hit_kf(pos.x(), pos.y())
            if hit is not None:
                ti, ki = hit
                kf   = self._tracks[ti]["keyframes"][ki]
                mins = int(kf[0]) // 60
                secs = kf[0] - mins * 60
                tip  = (
                    f"时间: {mins}:{secs:05.2f}\n"
                    f"X (左右): {kf[1]:+.3f}\n"
                    f"Z (前后): {kf[2]:+.3f}\n"
                    f"Y (高度): {kf[3]:+.3f}"
                )
                QToolTip.showText(event.globalPosition().toPoint(), tip, self)
            else:
                QToolTip.hideText()

    def mouseReleaseEvent(self, _event: QMouseEvent):
        self._drag_playhead = False
        self._drag_kf       = None

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            factor = 1.15 if delta > 0 else 1 / 1.15
            self._pixels_per_sec = max(5.0, min(400.0,
                                                self._pixels_per_sec * factor))
        else:
            self._scroll_x = max(0.0, self._scroll_x - delta * 0.5)
        self.update()

    # ── Context menu ──────────────────────────────────────────────

    def _show_kf_menu(self, hit: tuple[int, int], global_pos):
        ti, ki  = hit
        track   = self._tracks[ti]
        kf      = track["keyframes"][ki]
        tid     = track["id"]

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{ background:#2A2A2A; border:1px solid #444; color:{TEXT_PRIMARY}; }}
            QMenu::item:selected {{ background:{ACCENT}; color:#000; }}
            QMenu::separator {{ background:#444; height:1px; margin:3px 0; }}
        """)

        mins   = int(kf[0]) // 60
        secs   = kf[0] - mins * 60
        info   = f"{mins}:{secs:05.2f}  X{kf[1]:+.1f} Z{kf[2]:+.1f} Y{kf[3]:+.1f}"
        info_a = QAction(info, menu)
        info_a.setEnabled(False)
        menu.addAction(info_a)
        menu.addSeparator()

        del_act   = menu.addAction("删除此关键帧")
        clear_act = menu.addAction(
            f"清除此音轨全部关键帧 ({len(track['keyframes'])} 个)"
        )

        chosen = menu.exec(global_pos)
        if chosen == del_act:
            self._selected_kf = None
            self.keyframe_deleted.emit(tid, ki)
        elif chosen == clear_act:
            self._selected_kf = None
            self.keyframes_cleared.emit(tid)

    # ── Hit testing ───────────────────────────────────────────────

    def _hit_kf(self, mx: float, my: float) -> tuple[int, int] | None:
        for ti, track in enumerate(self._tracks):
            cy = RULER_H + ti * ROW_H + ROW_H // 2
            if abs(my - cy) > KF_HALF + 4:
                continue
            for ki, kf in enumerate(track.get("keyframes", [])):
                kx = self._t2x(kf[0])
                if abs(mx - kx) < KF_HALF + 4:
                    return (ti, ki)
        return None

    def _hit_segment(self, mx: float, my: float) -> tuple[int, int] | None:
        """Return (track_index, segment_index) if click is on a segment line."""
        for ti, track in enumerate(self._tracks):
            cy  = RULER_H + ti * ROW_H + ROW_H // 2
            seg_cy = cy + SEG_Y_OFF
            if abs(my - seg_cy) > 6:
                continue
            kfs  = track.get("keyframes", [])
            segs = track.get("segments", [])
            for si in range(min(len(segs), len(kfs) - 1)):
                x_a = self._t2x(kfs[si][0])
                x_b = self._t2x(kfs[si + 1][0])
                if x_a < mx < x_b:
                    return (ti, si)
        return None

    def _y2track(self, y: float) -> int | None:
        idx = int((y - RULER_H) / ROW_H)
        return None if idx < 0 else idx
