import numpy as np

from src.scene.sphere import SoundSphere


def _ray_sphere_intersect(
    origin: np.ndarray, direction: np.ndarray, center: np.ndarray, radius: float
) -> float | None:
    oc = origin - center
    a = np.dot(direction, direction)
    b = 2.0 * np.dot(oc, direction)
    c = np.dot(oc, oc) - radius * radius
    discriminant = b * b - 4 * a * c
    if discriminant < 0:
        return None
    sqrt_disc = np.sqrt(discriminant)
    t1 = (-b - sqrt_disc) / (2 * a)
    t2 = (-b + sqrt_disc) / (2 * a)
    if t1 > 0:
        return t1
    if t2 > 0:
        return t2
    return None


class RaycastPicker:
    """Handles mouse-to-3D raycasting for sphere picking and dragging."""

    def __init__(self, gl_widget):
        self.gl_widget = gl_widget
        self.spheres: list[SoundSphere] = []
        self._dragging: SoundSphere | None = None
        self._drag_plane_normal: np.ndarray | None = None
        self._drag_plane_d: float = 0.0
        self._drag_offset: np.ndarray = np.zeros(3)

    def screen_to_ray(self, screen_x: float, screen_y: float):
        w = self.gl_widget
        width = w.width()
        height = w.height()
        if width == 0 or height == 0:
            return np.zeros(3), np.array([0, 0, -1.0])

        view_matrix = np.array(w.viewMatrix().data(), dtype=np.float64).reshape(4, 4).T
        region = (0, 0, width, height)
        viewport = (0, 0, width, height)
        proj_matrix = np.array(w.projectionMatrix(region, viewport).data(), dtype=np.float64).reshape(4, 4).T

        ndc_x = (2.0 * screen_x / width) - 1.0
        ndc_y = 1.0 - (2.0 * screen_y / height)

        inv_proj = np.linalg.inv(proj_matrix)
        inv_view = np.linalg.inv(view_matrix)

        clip = np.array([ndc_x, ndc_y, -1.0, 1.0])
        eye = inv_proj @ clip
        eye = np.array([eye[0], eye[1], -1.0, 0.0])

        world_dir = (inv_view @ eye)[:3]
        world_dir = world_dir / np.linalg.norm(world_dir)

        cp = w.cameraPosition()
        cam_pos = np.array([cp.x(), cp.y(), cp.z()], dtype=np.float64)
        return cam_pos, world_dir

    def pick(self, screen_x: float, screen_y: float) -> SoundSphere | None:
        origin, direction = self.screen_to_ray(screen_x, screen_y)
        closest = None
        min_t = float("inf")
        for sphere in self.spheres:
            t = _ray_sphere_intersect(origin, direction, sphere.position, sphere.radius * 2.0)
            if t is not None and t < min_t:
                min_t = t
                closest = sphere
        return closest

    def begin_drag(self, sphere: SoundSphere, screen_x: float, screen_y: float):
        self._dragging = sphere
        cam_pos, _ = self.screen_to_ray(screen_x, screen_y)
        view_dir = sphere.position - cam_pos
        view_dir = view_dir / np.linalg.norm(view_dir)

        self._drag_plane_normal = -view_dir
        self._drag_plane_d = np.dot(self._drag_plane_normal, sphere.position)

        hit = self._intersect_plane(screen_x, screen_y)
        if hit is not None:
            self._drag_offset = sphere.position - hit

    def update_drag(self, screen_x: float, screen_y: float) -> np.ndarray | None:
        if self._dragging is None:
            return None
        hit = self._intersect_plane(screen_x, screen_y)
        if hit is not None:
            new_pos = hit + self._drag_offset
            self._dragging.position = new_pos
            return new_pos
        return None

    def end_drag(self) -> SoundSphere | None:
        sphere = self._dragging
        self._dragging = None
        return sphere

    @property
    def is_dragging(self) -> bool:
        return self._dragging is not None

    @property
    def dragged_sphere(self) -> SoundSphere | None:
        return self._dragging

    def _intersect_plane(self, screen_x: float, screen_y: float) -> np.ndarray | None:
        origin, direction = self.screen_to_ray(screen_x, screen_y)
        denom = np.dot(self._drag_plane_normal, direction)
        if abs(denom) < 1e-8:
            return None
        t = (self._drag_plane_d - np.dot(self._drag_plane_normal, origin)) / denom
        if t < 0:
            return None
        return origin + t * direction
