import numpy as np

from src.constants import MAX_DISTANCE


class SpatialMapper:
    """Maps 3D position to audio parameters (gain, pan, LPF cutoff)."""

    def __init__(self, max_distance: float = MAX_DISTANCE):
        self.max_distance = max_distance

    def compute(self, pos) -> tuple[float, float, float]:
        pos = np.asarray(pos, dtype=np.float64)
        x, y, z = pos
        d = np.linalg.norm(pos)

        gain = 1.0 / (1.0 + (d / self.max_distance) ** 2)

        cutoff = 200.0 + (20000.0 - 200.0) * np.exp(-0.3 * d)

        pan = float(np.clip(x / self.max_distance, -1.0, 1.0))

        return float(gain), pan, float(cutoff)
