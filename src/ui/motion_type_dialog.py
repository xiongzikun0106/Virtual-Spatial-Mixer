"""
Motion Type Selection Dialog.

Shows available motion types, a real-function rate curve graph,
and a custom bezier curve editor.
"""

import math

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QWidget, QButtonGroup,
)
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont,
)

from src.core.trajectory import (
    MotionType, MOTION_NAMES, MOTION_FORMULAS, Segment,
)
from src.ui.theme import (
    BG_PANEL, BG_LIGHTER, TEXT_PRIMARY, TEXT_SECONDARY,
    BORDER_COLOR, ACCENT, MONO_FONT,
)


class CurveGraph(QWidget):
    """Displays the rate curve for a given MotionType using the real function."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(210, 170)
        self._motion_type   = MotionType.LINEAR
        self._custom_points: list = []

    def set_motion_type(self, mt: MotionType, custom_pts: list | None = None):
        self._motion_type   = mt
        self._custom_points = list(custom_pts) if custom_pts else []
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        m = 22

        p.fillRect(0, 0, w, h, QColor("#141414"))

        # Grid
        p.setPen(QPen(QColor("#222222"), 1))
        pw = w - 2 * m
        ph = h - 2 * m
        for i in range(1, 4):
            gx = int(m + pw * i / 4)
            gy = int(m + ph * i / 4)
            p.drawLine(gx, m, gx, h - m)
            p.drawLine(m, gy, w - m, gy)

        # Axes
        p.setPen(QPen(QColor("#3A3A3A"), 1))
        p.drawLine(m, m, m, h - m)
        p.drawLine(m, h - m, w - m, h - m)

        # Axis labels
        font = QFont(MONO_FONT, 6)
        p.setFont(font)
        p.setPen(QColor("#555555"))
        p.drawText(m - 6, h - m + 13, "0")
        p.drawText(w - m - 3, h - m + 13, "1")
        p.drawText(2, h - m + 3, "0")
        p.drawText(2, m + 5, "1")
        p.drawText(w // 2 - 3, h - 4, "t")
        p.drawText(2, m - 6, "f")

        def to_px(t: float, ft: float) -> QPointF:
            px = m + t * pw
            py = (h - m) - ft * ph
            return QPointF(px, py)

        mt = self._motion_type
        n  = 100

        def sample(t: float) -> float:
            if mt == MotionType.LINEAR:
                return t
            elif mt == MotionType.EASE_IN:
                return t * t
            elif mt == MotionType.EASE_OUT:
                return 1.0 - (1.0 - t) ** 2
            elif mt == MotionType.EASE_IN_OUT:
                return 0.5 * (1.0 - math.cos(math.pi * t))
            elif mt == MotionType.ORBIT:
                # Show the X component of the circular path
                return 0.5 + 0.5 * math.cos(2.0 * math.pi * t)
            elif mt == MotionType.CUSTOM and len(self._custom_points) >= 2:
                seg = Segment(motion_type=MotionType.CUSTOM,
                              custom_bezier=self._custom_points)
                return seg.apply_easing(t)
            return t

        pts = [to_px(i / n, sample(i / n)) for i in range(n + 1)]

        # Reference diagonal
        p.setPen(QPen(QColor("#333333"), 1, Qt.PenStyle.DashLine))
        p.drawLine(to_px(0, 0), to_px(1, 1))

        # Curve
        p.setPen(QPen(QColor(ACCENT), 2))
        for i in range(len(pts) - 1):
            p.drawLine(pts[i], pts[i + 1])

        p.end()


class CustomCurveEditor(QWidget):
    """Piecewise-linear custom curve editor with draggable interior control points."""

    _MARGIN = 22
    _HIT_R  = 7

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(210, 170)
        self.setMouseTracking(True)
        # Control points: list of (t, p) in [0,1]×[0,1]
        self._pts: list[tuple[float, float]] = [
            (0.0, 0.0), (0.33, 0.33), (0.67, 0.67), (1.0, 1.0)
        ]
        self._dragging_idx: int | None = None

    def get_points(self) -> list[tuple[float, float]]:
        return list(self._pts)

    def set_points(self, pts: list[tuple[float, float]]):
        self._pts = list(pts)
        self.update()

    # ── Geometry helpers ───────────────────────────────────────────

    def _to_px(self, t: float, p: float) -> QPointF:
        m  = self._MARGIN
        pw = self.width()  - 2 * m
        ph = self.height() - 2 * m
        return QPointF(m + t * pw, (self.height() - m) - p * ph)

    def _from_px(self, px: float, py: float) -> tuple[float, float]:
        m  = self._MARGIN
        pw = self.width()  - 2 * m
        ph = self.height() - 2 * m
        t = max(0.0, min(1.0, (px - m) / pw))
        p = max(0.0, min(1.0, ((self.height() - m) - py) / ph))
        return t, p

    # ── Paint ─────────────────────────────────────────────────────

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        m = self._MARGIN

        painter.fillRect(0, 0, w, h, QColor("#141414"))

        # Grid
        pw, ph = w - 2 * m, h - 2 * m
        painter.setPen(QPen(QColor("#222222"), 1))
        for i in range(1, 4):
            gx = int(m + pw * i / 4)
            gy = int(m + ph * i / 4)
            painter.drawLine(gx, m, gx, h - m)
            painter.drawLine(m, gy, w - m, gy)

        # Axes
        painter.setPen(QPen(QColor("#3A3A3A"), 1))
        painter.drawLine(m, m, m, h - m)
        painter.drawLine(m, h - m, w - m, h - m)

        # Curve
        if len(self._pts) >= 2:
            px_pts = [self._to_px(t, p) for t, p in self._pts]
            painter.setPen(QPen(QColor(ACCENT), 2))
            for i in range(len(px_pts) - 1):
                painter.drawLine(px_pts[i], px_pts[i + 1])

        # Control points
        for i, (t, p) in enumerate(self._pts):
            ppt = self._to_px(t, p)
            is_endpoint = i == 0 or i == len(self._pts) - 1
            painter.setPen(QPen(QColor("white"), 1))
            color = QColor("#888888") if is_endpoint else QColor(ACCENT)
            painter.setBrush(QBrush(color))
            painter.drawEllipse(ppt, 5, 5)

        painter.end()

    # ── Mouse ─────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        px = event.position().x()
        py = event.position().y()
        for i in range(1, len(self._pts) - 1):
            ppt = self._to_px(*self._pts[i])
            if abs(px - ppt.x()) < self._HIT_R and abs(py - ppt.y()) < self._HIT_R:
                self._dragging_idx = i
                return

    def mouseMoveEvent(self, event):
        if self._dragging_idx is None:
            return
        t, p = self._from_px(event.position().x(), event.position().y())
        # Keep t between neighbors
        prev_t = self._pts[self._dragging_idx - 1][0]
        next_t = self._pts[self._dragging_idx + 1][0]
        t = max(prev_t + 0.01, min(next_t - 0.01, t))
        self._pts[self._dragging_idx] = (t, p)
        self.update()

    def mouseReleaseEvent(self, _event):
        self._dragging_idx = None


class MotionTypeDialog(QDialog):
    """Dialog for selecting segment motion type with real rate curve visualization."""

    def __init__(self, segment: Segment, parent=None):
        super().__init__(parent)
        self.setWindowTitle("运动方式设置")
        self.setModal(True)
        self.setFixedSize(560, 420)
        self.setStyleSheet(f"""
            QDialog   {{ background-color: {BG_PANEL}; color: {TEXT_PRIMARY}; }}
            QLabel    {{ color: {TEXT_PRIMARY}; }}
        """)

        self._segment = segment
        self.selected_motion_type: MotionType = segment.motion_type
        self.custom_bezier_points: list = (
            list(segment.custom_bezier) if segment.custom_bezier
            else [(0.0, 0.0), (0.33, 0.33), (0.67, 0.67), (1.0, 1.0)]
        )

        self._build_ui()
        self._select(segment.motion_type)

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        main = QHBoxLayout(self)
        main.setSpacing(14)
        main.setContentsMargins(14, 14, 14, 14)

        # ── Left column: motion type buttons ──────────────────────
        left = QVBoxLayout()
        left.setSpacing(5)
        hdr = QLabel("运动方式")
        hdr.setStyleSheet(f"color:{TEXT_SECONDARY}; font-size:10px; font-weight:bold;")
        left.addWidget(hdr)

        self._btns: dict[MotionType, QPushButton] = {}
        btn_style_tpl = """
            QPushButton {{
                background:{bg}; color:{fg};
                border: 1px solid {border}; border-radius: 3px;
                font-size: 12px; padding: 6px 10px; text-align: left;
            }}
            QPushButton:checked {{
                background: {accent}; color: #000; border-color: {accent};
            }}
            QPushButton:hover {{ border-color: {accent}; }}
        """.format(bg=BG_LIGHTER, fg=TEXT_PRIMARY, border=BORDER_COLOR, accent=ACCENT)

        for mt in MotionType:
            btn = QPushButton(MOTION_NAMES[mt])
            btn.setCheckable(True)
            btn.setFixedHeight(34)
            btn.setFixedWidth(120)
            btn.setStyleSheet(btn_style_tpl)
            btn.clicked.connect(lambda _checked, m=mt: self._select(m))
            self._btns[mt] = btn
            left.addWidget(btn)

        left.addStretch()
        main.addLayout(left)

        # ── Right column: graph + formula + custom editor + buttons ─
        right = QVBoxLayout()
        right.setSpacing(8)

        self._formula_lbl = QLabel()
        self._formula_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:10px; font-family:monospace;"
        )
        self._formula_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self._formula_lbl)

        self._curve_graph = CurveGraph()
        right.addWidget(self._curve_graph, alignment=Qt.AlignmentFlag.AlignCenter)

        self._custom_lbl = QLabel("自定义曲线 — 拖动中间控制点")
        self._custom_lbl.setStyleSheet(
            f"color:{TEXT_SECONDARY}; font-size:9px;"
        )
        self._custom_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._custom_lbl.setVisible(False)
        right.addWidget(self._custom_lbl)

        self._custom_editor = CustomCurveEditor()
        self._custom_editor.set_points(self.custom_bezier_points)
        self._custom_editor.setVisible(False)
        right.addWidget(self._custom_editor, alignment=Qt.AlignmentFlag.AlignCenter)

        right.addStretch()

        # Buttons
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("应用")
        ok_btn.setStyleSheet(f"""
            QPushButton {{
                background:{ACCENT}; color:#000; border:none;
                border-radius:3px; font-size:11px; padding:6px 20px;
            }}
            QPushButton:hover {{ background:#00E5FF; }}
        """)
        ok_btn.clicked.connect(self._on_apply)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background:{BG_LIGHTER}; color:{TEXT_PRIMARY};
                border:1px solid {BORDER_COLOR}; border-radius:3px;
                font-size:11px; padding:6px 20px;
            }}
            QPushButton:hover {{ border-color:{ACCENT}; }}
        """)
        cancel_btn.clicked.connect(self.reject)

        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        right.addLayout(btn_row)

        main.addLayout(right)

    # ── Interaction ───────────────────────────────────────────────

    def _select(self, mt: MotionType):
        self.selected_motion_type = mt
        for m, btn in self._btns.items():
            btn.setChecked(m == mt)
        self._formula_lbl.setText(MOTION_FORMULAS[mt])
        self._curve_graph.set_motion_type(mt, self.custom_bezier_points)
        is_custom = mt == MotionType.CUSTOM
        self._custom_lbl.setVisible(is_custom)
        self._custom_editor.setVisible(is_custom)

    def _on_apply(self):
        if self.selected_motion_type == MotionType.CUSTOM:
            self.custom_bezier_points = self._custom_editor.get_points()
        self.accept()
