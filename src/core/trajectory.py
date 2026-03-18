import numpy as np
from scipy.interpolate import CubicSpline


class Trajectory:
    """Stores and interpolates a track's spatial trajectory over time.

    Supports two modes:
    - Keyframe editing: manually placed keyframes with spline interpolation
    - Real-time recording: high-frequency position sampling during playback
    """

    def __init__(self):
        self.keyframes: list[tuple[float, float, float, float]] = []  # (t, x, y, z)
        self._spline: CubicSpline | None = None
        self._dirty = True

    @property
    def duration(self) -> float:
        if not self.keyframes:
            return 0.0
        return self.keyframes[-1][0] - self.keyframes[0][0]

    @property
    def start_time(self) -> float:
        return self.keyframes[0][0] if self.keyframes else 0.0

    @property
    def end_time(self) -> float:
        return self.keyframes[-1][0] if self.keyframes else 0.0

    def add_keyframe(self, t: float, x: float, y: float, z: float):
        self.keyframes.append((t, x, y, z))
        self.keyframes.sort(key=lambda kf: kf[0])
        self._dirty = True

    def remove_keyframe(self, index: int):
        if 0 <= index < len(self.keyframes):
            self.keyframes.pop(index)
            self._dirty = True

    def move_keyframe(self, index: int, t: float, x: float, y: float, z: float):
        if 0 <= index < len(self.keyframes):
            self.keyframes[index] = (t, x, y, z)
            self.keyframes.sort(key=lambda kf: kf[0])
            self._dirty = True

    def record_frame(self, t: float, x: float, y: float, z: float):
        self.keyframes.append((t, x, y, z))
        self._dirty = True

    def finish_recording(self, tolerance: float = 0.05):
        """Simplify recorded trajectory using distance-based decimation."""
        if len(self.keyframes) < 3:
            self._rebuild()
            return
        simplified = [self.keyframes[0]]
        for i in range(1, len(self.keyframes) - 1):
            prev = np.array(simplified[-1][1:])
            curr = np.array(self.keyframes[i][1:])
            if np.linalg.norm(curr - prev) >= tolerance:
                simplified.append(self.keyframes[i])
        simplified.append(self.keyframes[-1])
        self.keyframes = simplified
        self._dirty = True
        self._rebuild()

    def _rebuild(self):
        if len(self.keyframes) < 2:
            self._spline = None
            self._dirty = False
            return
        times = np.array([kf[0] for kf in self.keyframes])
        positions = np.array([[kf[1], kf[2], kf[3]] for kf in self.keyframes])

        unique_mask = np.diff(times, prepend=-np.inf) > 1e-6
        times = times[unique_mask]
        positions = positions[unique_mask]

        if len(times) < 2:
            self._spline = None
            self._dirty = False
            return

        self._spline = CubicSpline(times, positions, bc_type="clamped")
        self._dirty = False

    def get_position(self, t: float) -> np.ndarray:
        if self._dirty:
            self._rebuild()
        if self._spline is None:
            if self.keyframes:
                return np.array(self.keyframes[0][1:])
            return np.zeros(3)
        t = np.clip(t, self.keyframes[0][0], self.keyframes[-1][0])
        return self._spline(t)

    def get_curve_points(self, num_points: int = 200) -> np.ndarray | None:
        if self._dirty:
            self._rebuild()
        if self._spline is None or len(self.keyframes) < 2:
            return None
        t_start = self.keyframes[0][0]
        t_end = self.keyframes[-1][0]
        times = np.linspace(t_start, t_end, num_points)
        return self._spline(times)

    def clear(self):
        self.keyframes.clear()
        self._spline = None
        self._dirty = True

    def to_list(self) -> list[list[float]]:
        return [[t, x, y, z] for t, x, y, z in self.keyframes]

    @classmethod
    def from_list(cls, data: list[list[float]]) -> "Trajectory":
        traj = cls()
        for item in data:
            traj.keyframes.append(tuple(item))
        traj._dirty = True
        return traj
