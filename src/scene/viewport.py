import numpy as np
import pyqtgraph.opengl as gl
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from src.scene.grid import GridFloor
from src.scene.sphere import SoundSphere
from src.scene.trajectory_renderer import TrajectoryRenderer
from src.constants import SPHERE_RADIUS


class Viewport3D(QWidget):
    """Read-only 3D preview viewport.

    All position control is handled by TrackPanel controls.
    This widget only displays sphere positions, trajectories and coordinate labels.
    Mouse interaction is limited to camera orbit/pan/zoom (provided by GLViewWidget).
    """

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

        self.trajectory_renderer = TrajectoryRenderer()
        self.spheres: dict[int, SoundSphere] = {}
        self._labels: dict[int, gl.GLTextItem] = {}

    def _add_origin_marker(self):
        axis_len = 3.0
        # Axes: internal coords are X=right, Y=front(user's Z), Z=up(user's Y)
        axes = [
            (np.array([[0, 0, 0], [axis_len, 0, 0]]),  (1.0, 0.3, 0.3, 0.9)),   # +X right
            (np.array([[0, 0, 0], [-axis_len, 0, 0]]), (1.0, 0.3, 0.3, 0.35)),  # -X left
            (np.array([[0, 0, 0], [0, axis_len, 0]]),  (0.3, 0.5, 1.0, 0.9)),   # +Y front (user Z)
            (np.array([[0, 0, 0], [0, -axis_len, 0]]), (0.3, 0.5, 1.0, 0.35)),  # -Y back (user -Z)
            (np.array([[0, 0, 0], [0, 0, axis_len]]),  (0.3, 1.0, 0.3, 0.6)),   # +Z up (user Y)
        ]
        for pts, color in axes:
            item = gl.GLLinePlotItem(pos=pts, color=color, width=2.0, antialias=True)
            self.gl_widget.addItem(item)

        label_offset = axis_len + 0.6
        # Labels use user-facing convention: X=right, Z=front/back, Y=height
        labels = [
            (np.array([label_offset, 0, 0]),   "+X  右",  (255, 80,  80,  255)),
            (np.array([-label_offset, 0, 0]),  "-X  左",  (255, 80,  80,  160)),
            (np.array([0, label_offset, 0]),   "+Z  前",  (80,  130, 255, 255)),
            (np.array([0, -label_offset, 0]),  "-Z  后",  (80,  130, 255, 160)),
            (np.array([0, 0, label_offset]),   "+Y  上",  (80,  220, 80,  220)),
        ]
        for pos, text, color in labels:
            text_item = gl.GLTextItem(pos=pos, text=text, color=color)
            self.gl_widget.addItem(text_item)

        # Listener head outline
        head_size = 0.5
        head_pts = np.array([
            [0,               head_size,         0.02],
            [-head_size * 0.4, -head_size * 0.2, 0.02],
            [0,               0,                 0.02],
            [head_size * 0.4, -head_size * 0.2,  0.02],
            [0,               head_size,         0.02],
        ])
        head_item = gl.GLLinePlotItem(
            pos=head_pts, color=(1, 1, 1, 0.5), width=2.0, antialias=True,
        )
        self.gl_widget.addItem(head_item)

        # Origin dot
        origin = gl.GLScatterPlotItem(
            pos=np.array([[0, 0, 0]]),
            color=(1, 1, 1, 0.9),
            size=10,
            pxMode=True,
        )
        self.gl_widget.addItem(origin)

    # ── Sphere management ────────────────────────────────────────

    def add_sphere(self, track_id: int, color: tuple[int, int, int],
                   position: tuple[float, float, float]):
        sphere = SoundSphere(track_id, color, position)
        self.spheres[track_id] = sphere
        self.gl_widget.addItem(sphere.mesh_item)

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
        if track_id in self._labels:
            self.gl_widget.removeItem(self._labels.pop(track_id))

    def set_sphere_position(self, track_id: int, pos: tuple[float, float, float]):
        if track_id in self.spheres:
            self.spheres[track_id].position = pos
        if track_id in self._labels:
            ix, iy, iz = pos
            self._labels[track_id].setData(
                pos=np.array([ix, iy, iz + 0.55]),
                text=self._coord_text(ix, iy, iz),
            )

    def update_trajectory(self, track_id: int, points, color: tuple[int, int, int]):
        self.trajectory_renderer.update(track_id, points, color, self.gl_widget)

    @staticmethod
    def _coord_text(ix: float, iy: float, iz: float) -> str:
        # Display in user convention: X=right, Z=front/back (internal Y), Y=height (internal Z)
        return f"X:{ix:.1f}  Z:{iy:.1f}  Y:{iz:.1f}"
