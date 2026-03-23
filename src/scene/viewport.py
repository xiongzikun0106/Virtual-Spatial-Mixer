"""
Viewport3D – 3D preview with sphere dragging.

Camera orbit/pan/zoom: right-click or middle-click drag (GLViewWidget default).
Sphere drag:           left-click on a sphere, then drag to move it in 3D.

Signals
-------
sphere_dragged(track_id, ix, iy, iz)   emitted continuously while dragging
sphere_released(track_id)              emitted on mouse release after drag
"""

import numpy as np
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QMouseEvent
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from src.scene.grid import GridFloor
from src.scene.sphere import SoundSphere
from src.scene.trajectory_renderer import TrajectoryRenderer
from src.scene.picker import RaycastPicker
from src.constants import SPHERE_RADIUS


class _DraggableGLWidget(gl.GLViewWidget):
    """GLViewWidget subclass that delegates left-click sphere dragging."""

    def __init__(self, picker: "RaycastPicker", parent=None):
        super().__init__(parent)
        self._picker = picker
        self._sphere_drag_active = False

    def mousePressEvent(self, ev: QMouseEvent):
        if ev.button() == Qt.MouseButton.LeftButton:
            sphere = self._picker.pick(ev.position().x(), ev.position().y())
            if sphere is not None:
                self._picker.begin_drag(sphere, ev.position().x(), ev.position().y())
                self._sphere_drag_active = True
                ev.accept()
                return
        self._sphere_drag_active = False
        super().mousePressEvent(ev)

    def mouseMoveEvent(self, ev: QMouseEvent):
        if self._sphere_drag_active and self._picker.is_dragging:
            self._picker.update_drag(ev.position().x(), ev.position().y())
            ev.accept()
            return
        super().mouseMoveEvent(ev)

    def mouseReleaseEvent(self, ev: QMouseEvent):
        if self._sphere_drag_active:
            self._picker.end_drag()
            self._sphere_drag_active = False
            ev.accept()
            return
        super().mouseReleaseEvent(ev)


class Viewport3D(QWidget):
    """3D preview viewport with optional sphere-drag position control."""

    sphere_dragged  = pyqtSignal(int, float, float, float)  # tid, ix, iy, iz
    sphere_released = pyqtSignal(int)                        # tid

    def __init__(self, parent=None):
        super().__init__(parent)

        self._picker = RaycastPicker(None)  # gl_widget set below

        self.gl_widget = _DraggableGLWidget(self._picker)
        self.gl_widget.setCameraPosition(distance=15, elevation=30, azimuth=45)
        self.gl_widget.setBackgroundColor("#1A1A1A")
        self._picker.gl_widget = self.gl_widget

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gl_widget)

        self.grid = GridFloor()
        self.grid.add_to(self.gl_widget)
        self._add_origin_marker()

        self.trajectory_renderer = TrajectoryRenderer()
        self.spheres: dict[int, SoundSphere] = {}
        self._labels: dict[int, gl.GLTextItem] = {}

        # Poll dragging state via timer driven by app sync tick
        self._drag_poll_track: int | None = None

    def _add_origin_marker(self):
        axis_len = 3.0
        axes = [
            (np.array([[0, 0, 0], [axis_len, 0, 0]]),   (1.0, 0.3, 0.3, 0.9)),
            (np.array([[0, 0, 0], [-axis_len, 0, 0]]),  (1.0, 0.3, 0.3, 0.35)),
            (np.array([[0, 0, 0], [0, axis_len, 0]]),   (0.3, 0.5, 1.0, 0.9)),
            (np.array([[0, 0, 0], [0, -axis_len, 0]]),  (0.3, 0.5, 1.0, 0.35)),
            (np.array([[0, 0, 0], [0, 0, axis_len]]),   (0.3, 1.0, 0.3, 0.6)),
        ]
        for pts, color in axes:
            item = gl.GLLinePlotItem(
                pos=pts, color=color, width=2.0, antialias=True
            )
            self.gl_widget.addItem(item)

        label_offset = axis_len + 0.6
        labels = [
            (np.array([label_offset,  0, 0]),   "+X  右",  (255, 80,  80,  255)),
            (np.array([-label_offset, 0, 0]),   "-X  左",  (255, 80,  80,  160)),
            (np.array([0,  label_offset, 0]),   "+Z  前",  (80,  130, 255, 255)),
            (np.array([0, -label_offset, 0]),   "-Z  后",  (80,  130, 255, 160)),
            (np.array([0, 0,  label_offset]),   "+Y  上",  (80,  220, 80,  220)),
        ]
        for pos, text, color in labels:
            text_item = gl.GLTextItem(pos=pos, text=text, color=color)
            self.gl_widget.addItem(text_item)

        # Listener head outline
        head_size = 0.5
        head_pts = np.array([
            [0,                head_size,          0.02],
            [-head_size * 0.4, -head_size * 0.2,   0.02],
            [0,                0,                  0.02],
            [head_size * 0.4,  -head_size * 0.2,   0.02],
            [0,                head_size,           0.02],
        ])
        self.gl_widget.addItem(
            gl.GLLinePlotItem(
                pos=head_pts, color=(1, 1, 1, 0.5), width=2.0, antialias=True
            )
        )

        self.gl_widget.addItem(
            gl.GLScatterPlotItem(
                pos=np.array([[0, 0, 0]]),
                color=(1, 1, 1, 0.9), size=10, pxMode=True,
            )
        )

    # ── Sphere management ─────────────────────────────────────────

    def add_sphere(self, track_id: int, color: tuple[int, int, int],
                   position: tuple[float, float, float]):
        sphere = SoundSphere(track_id, color, position)
        self.spheres[track_id] = sphere
        self.gl_widget.addItem(sphere.mesh_item)
        self._picker.spheres.append(sphere)

        ix, iy, iz = position
        label = gl.GLTextItem(
            pos=np.array([ix, iy, iz + 0.55]),
            text=self._coord_text(ix, iy, iz),
            color=(210, 210, 210, 200),
        )
        self._labels[track_id] = label
        self.gl_widget.addItem(label)
        return sphere

    def remove_sphere(self, track_id: int):
        if track_id in self.spheres:
            sphere = self.spheres.pop(track_id)
            self.gl_widget.removeItem(sphere.mesh_item)
            self.trajectory_renderer.remove(track_id, self.gl_widget)
            if sphere in self._picker.spheres:
                self._picker.spheres.remove(sphere)
        if track_id in self._labels:
            self.gl_widget.removeItem(self._labels.pop(track_id))

    def set_sphere_position(self, track_id: int,
                            pos: tuple[float, float, float]):
        if track_id in self.spheres:
            self.spheres[track_id].position = pos
        if track_id in self._labels:
            ix, iy, iz = pos
            self._labels[track_id].setData(
                pos=np.array([ix, iy, iz + 0.55]),
                text=self._coord_text(ix, iy, iz),
            )

    def update_trajectory(self, track_id: int, points,
                          color: tuple[int, int, int]):
        self.trajectory_renderer.update(track_id, points, color, self.gl_widget)

    def poll_drag(self) -> tuple[int, tuple[float, float, float]] | None:
        """
        Called every sync tick.  Returns (track_id, (ix, iy, iz)) if a sphere
        is currently being dragged, else None.
        """
        sphere = self._picker.dragged_sphere
        if sphere is None:
            return None
        tid = sphere.track_id
        pos = tuple(float(v) for v in sphere.position)
        return tid, pos  # type: ignore[return-value]

    # ── Helpers ───────────────────────────────────────────────────

    @staticmethod
    def _coord_text(ix: float, iy: float, iz: float) -> str:
        return f"X:{ix:.1f}  Z:{iy:.1f}  Y:{iz:.1f}"
