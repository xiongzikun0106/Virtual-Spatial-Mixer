import numpy as np

from src.constants import COLLISION_THRESHOLD, COLLISION_DUCK_RATIO


class CollisionResolver:
    """Auto-ducking when sound spheres are too close together."""

    def __init__(
        self,
        threshold: float = COLLISION_THRESHOLD,
        duck_ratio: float = COLLISION_DUCK_RATIO,
    ):
        self.threshold = threshold
        self.duck_ratio = duck_ratio

    def resolve(self, tracks_with_positions: list[tuple]) -> dict[int, float]:
        """Return {track_id: duck_gain} for all tracks.

        tracks_with_positions: [(track_id, priority, np.array([x,y,z])), ...]
        """
        duck_gains: dict[int, float] = {}
        for tid, _, _ in tracks_with_positions:
            duck_gains[tid] = 1.0

        n = len(tracks_with_positions)
        for i in range(n):
            tid_i, pri_i, pos_i = tracks_with_positions[i]
            for j in range(i + 1, n):
                tid_j, pri_j, pos_j = tracks_with_positions[j]
                dist = float(np.linalg.norm(pos_i - pos_j))
                if dist < self.threshold:
                    overlap = 1.0 - (dist / self.threshold)
                    duck = 1.0 - overlap * self.duck_ratio
                    if pri_i >= pri_j:
                        duck_gains[tid_j] = min(duck_gains[tid_j], duck)
                    else:
                        duck_gains[tid_i] = min(duck_gains[tid_i], duck)

        return duck_gains
