import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QVBoxLayout, QWidget
from PyQt6.QtCore import pyqtSignal, Qt

from src.scene.grid import GridFloor
from src.scene.sphere import SoundSphere
from src.scene.picker import RaycastPicker
from src.scene.trajectory_renderer import TrajectoryRenderer
from src.constants import SPHERE_RADIUS


class Viewport3D(QWidget):
    """Wrapper around GLViewWidget with sphere picking/dragging support."""

    sphere_moved = pyqtSignal(int, float, float, float)  # track_id, x, y, z
    sphere_drag_started = pyqtSignal(int)
    sphere_drag_ended = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.gl_widget = gl.GLViewWidget()
        self.gl_widget.setCameraPosition(distance=15, elevation=30, azimuth=45)
        self.gl_widget.setBackgroundColor("#1A1A1A")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.gl_widget)

        self.grid = GridFloor()
        self.grid.add_to(self.gl_widget)

        self._add_origin_marker()

        self.picker = RaycastPicker(self.gl_widget)
        self.trajectory_renderer = TrajectoryRenderer()
        self.spheres: dict[int, SoundSphere] = {}

        self.gl_widget.installEventFilter(self)

    def _add_origin_marker(self):
        axis_len = 1.0
        axes = [
            (np.array([[0, 0, 0], [axis_len, 0, 0]]), (1.0, 0.3, 0.3, 0.8)),  # X red
            (np.array([[0, 0, 0], [0, axis_len, 0]]), (0.3, 1.0, 0.3, 0.8)),  # Y green
            (np.array([[0, 0, 0], [0, 0, axis_len]]), (0.3, 0.3, 1.0, 0.8)),  # Z blue
        ]
        for pts, color in axes:
            item = gl.GLLinePlotItem(pos=pts, color=color, width=2.0, antialias=True)
            self.gl_widget.addItem(item)

        origin = gl.GLScatterPlotItem(
            pos=np.array([[0, 0, 0]]),
            color=(1, 1, 1, 0.8),
            size=8,
            pxMode=True,
        )
        self.gl_widget.addItem(origin)

    def add_sphere(self, track_id: int, color: tuple[int, int, int], position: tuple[float, float, float]):
        sphere = SoundSphere(track_id, color, position)
        self.spheres[track_id] = sphere
        self.picker.spheres.append(sphere)
        self.gl_widget.addItem(sphere.mesh_item)
        return sphere

    def remove_sphere(self, track_id: int):
        if track_id in self.spheres:
            sphere = self.spheres.pop(track_id)
            self.gl_widget.removeItem(sphere.mesh_item)
            if sphere in self.picker.spheres:
                self.picker.spheres.remove(sphere)
            self.trajectory_renderer.remove(track_id, self.gl_widget)

    def set_sphere_position(self, track_id: int, pos: tuple[float, float, float]):
        if track_id in self.spheres:
            self.spheres[track_id].position = pos

    def update_trajectory(self, track_id: int, points: np.ndarray | None, color: tuple[int, int, int]):
        self.trajectory_renderer.update(track_id, points, color, self.gl_widget)

    def eventFilter(self, obj, event):
        from PyQt6.QtCore import QEvent

        if obj is not self.gl_widget:
            return False

        if event.type() == QEvent.Type.MouseButtonPress:
            if event.button() == Qt.MouseButton.LeftButton and event.modifiers() == Qt.KeyboardModifier.NoModifier:
                pos = event.position()
                sphere = self.picker.pick(pos.x(), pos.y())
                if sphere is not None:
                    self.picker.begin_drag(sphere, pos.x(), pos.y())
                    self.sphere_drag_started.emit(sphere.track_id)
                    return True

        elif event.type() == QEvent.Type.MouseMove:
            if self.picker.is_dragging:
                pos = event.position()
                new_pos = self.picker.update_drag(pos.x(), pos.y())
                if new_pos is not None:
                    self.sphere_moved.emit(
                        self.picker.dragged_sphere.track_id,
                        float(new_pos[0]),
                        float(new_pos[1]),
                        float(new_pos[2]),
                    )
                return True

        elif event.type() == QEvent.Type.MouseButtonRelease:
            if self.picker.is_dragging:
                sphere = self.picker.end_drag()
                if sphere is not None:
                    self.sphere_drag_ended.emit(sphere.track_id)
                return True

        return False
