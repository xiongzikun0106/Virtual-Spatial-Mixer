import numpy as np
import pyqtgraph.opengl as gl
from pyqtgraph.opengl import MeshData

from src.constants import SPHERE_RADIUS


def _make_sphere_mesh(radius: float, rows: int = 16, cols: int = 16) -> MeshData:
    verts = []
    faces = []
    for i in range(rows + 1):
        lat = np.pi * i / rows
        for j in range(cols):
            lon = 2 * np.pi * j / cols
            x = radius * np.sin(lat) * np.cos(lon)
            y = radius * np.sin(lat) * np.sin(lon)
            z = radius * np.cos(lat)
            verts.append([x, y, z])

    for i in range(rows):
        for j in range(cols):
            p1 = i * cols + j
            p2 = i * cols + (j + 1) % cols
            p3 = (i + 1) * cols + j
            p4 = (i + 1) * cols + (j + 1) % cols
            faces.append([p1, p2, p4])
            faces.append([p1, p4, p3])

    return MeshData(
        vertexes=np.array(verts, dtype=np.float32),
        faces=np.array(faces, dtype=np.uint32),
    )


_SPHERE_MD = None


def _get_sphere_md():
    global _SPHERE_MD
    if _SPHERE_MD is None:
        _SPHERE_MD = _make_sphere_mesh(SPHERE_RADIUS)
    return _SPHERE_MD


class SoundSphere:
    """A coloured sphere in 3D space representing an audio track."""

    def __init__(self, track_id: int, color: tuple[int, int, int], position: tuple[float, float, float] = (0, 0, 0)):
        self.track_id = track_id
        self.radius = SPHERE_RADIUS

        r, g, b = color
        self.color = (r / 255.0, g / 255.0, b / 255.0, 1.0)
        self.color_rgb = color

        self.mesh_item = gl.GLMeshItem(
            meshdata=_get_sphere_md(),
            smooth=True,
            color=self.color,
            shader="shaded",
            glOptions="opaque",
        )
        self._position = np.array(position, dtype=np.float64)
        self.mesh_item.translate(*position)

    @property
    def position(self) -> np.ndarray:
        return self._position.copy()

    @position.setter
    def position(self, pos):
        new = np.array(pos, dtype=np.float64)
        self.mesh_item.resetTransform()
        self.mesh_item.translate(*new)
        self._position = new

    def set_glow(self, intensity: float):
        """Adjust brightness to simulate glow based on gain."""
        r, g, b = self.color[:3]
        factor = 0.4 + 0.6 * max(0.0, min(1.0, intensity))
        self.mesh_item.setColor((r * factor, g * factor, b * factor, 1.0))
