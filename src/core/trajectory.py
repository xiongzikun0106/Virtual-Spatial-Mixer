"""
Trajectory – keyframe + segment motion model.

Structure:
    A --(Segment0)--> B --(Segment1)--> C

Each Keyframe stores: time, x, y, z
Each Segment stores:  motion_type, custom_bezier

Supported motion types:
    LINEAR      : f(t) = t
    EASE_IN     : f(t) = t²
    EASE_OUT    : f(t) = 1 − (1−t)²
    EASE_IN_OUT : f(t) = 0.5 × (1 − cos(πt))
    ORBIT       : circular arc path (not a standard interpolation)
    CUSTOM      : user-defined bezier curve
"""

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

import numpy as np


class MotionType(Enum):
    LINEAR      = "linear"
    EASE_IN     = "ease_in"
    EASE_OUT    = "ease_out"
    EASE_IN_OUT = "ease_in_out"
    ORBIT       = "orbit"
    CUSTOM      = "custom"


MOTION_NAMES: dict[MotionType, str] = {
    MotionType.LINEAR:      "匀速",
    MotionType.EASE_IN:     "慢→快",
    MotionType.EASE_OUT:    "快→慢",
    MotionType.EASE_IN_OUT: "平滑",
    MotionType.ORBIT:       "绕行",
    MotionType.CUSTOM:      "自定义",
}

MOTION_FORMULAS: dict[MotionType, str] = {
    MotionType.LINEAR:      "f(t) = t",
    MotionType.EASE_IN:     "f(t) = t²",
    MotionType.EASE_OUT:    "f(t) = 1 − (1−t)²",
    MotionType.EASE_IN_OUT: "f(t) = 0.5 × (1 − cos(πt))",
    MotionType.ORBIT:       "x = cos(2πt)  y = sin(2πt)",
    MotionType.CUSTOM:      "用户定义曲线",
}

# Color for each motion type when displayed in the timeline
MOTION_COLORS: dict[MotionType, str] = {
    MotionType.LINEAR:      "#888888",
    MotionType.EASE_IN:     "#FF9800",
    MotionType.EASE_OUT:    "#2196F3",
    MotionType.EASE_IN_OUT: "#9C27B0",
    MotionType.ORBIT:       "#4CAF50",
    MotionType.CUSTOM:      "#FFD600",
}


@dataclass
class Keyframe:
    time: float
    x: float
    y: float
    z: float

    def as_tuple(self) -> tuple:
        return (self.time, self.x, self.y, self.z)


@dataclass
class Segment:
    """Motion properties for the interval between two adjacent keyframes."""
    motion_type: MotionType = MotionType.LINEAR
    # Custom curve: list of (t, p) control points, both in [0, 1]
    custom_bezier: List = field(default_factory=list)

    def apply_easing(self, t: float) -> float:
        """Map normalized time t ∈ [0,1] → progress p ∈ [0,1]."""
        t = max(0.0, min(1.0, t))
        mt = self.motion_type
        if mt == MotionType.LINEAR:
            return t
        elif mt == MotionType.EASE_IN:
            return t * t
        elif mt == MotionType.EASE_OUT:
            return 1.0 - (1.0 - t) ** 2
        elif mt == MotionType.EASE_IN_OUT:
            return 0.5 * (1.0 - math.cos(math.pi * t))
        elif mt == MotionType.CUSTOM:
            return self._custom_ease(t)
        # ORBIT is handled externally
        return t

    def _custom_ease(self, t: float) -> float:
        pts = self.custom_bezier
        if len(pts) < 2:
            return t
        for i in range(len(pts) - 1):
            t0, p0 = pts[i]
            t1, p1 = pts[i + 1]
            if t0 <= t <= t1:
                if abs(t1 - t0) < 1e-9:
                    return float(p0)
                local = (t - t0) / (t1 - t0)
                return float(p0 + (p1 - p0) * local)
        return float(pts[-1][1])


class Trajectory:
    """
    Keyframe + segment trajectory model.

    _keyframes : sorted list of Keyframe objects
    _segments  : list of Segment objects, len == max(0, len(_keyframes) - 1)
                 _segments[i] governs motion from _keyframes[i] → _keyframes[i+1]
    """

    def __init__(self):
        self._keyframes: List[Keyframe] = []
        self._segments:  List[Segment]  = []

    # ── Backward-compatible properties ──────────────────────────────

    @property
    def keyframes(self) -> List[tuple]:
        """Legacy format: list of (time, x, y, z) tuples."""
        return [kf.as_tuple() for kf in self._keyframes]

    @property
    def kf_objects(self) -> List[Keyframe]:
        return self._keyframes

    @property
    def segments(self) -> List[Segment]:
        return self._segments

    @property
    def duration(self) -> float:
        if len(self._keyframes) < 2:
            return 0.0
        return self._keyframes[-1].time - self._keyframes[0].time

    @property
    def start_time(self) -> float:
        return self._keyframes[0].time if self._keyframes else 0.0

    @property
    def end_time(self) -> float:
        return self._keyframes[-1].time if self._keyframes else 0.0

    # ── Keyframe editing ────────────────────────────────────────────

    def add_keyframe(self, t: float, x: float, y: float, z: float):
        """Insert a keyframe at time t (sorted). Adjusts segment list."""
        kf = Keyframe(time=t, x=x, y=y, z=z)
        n_before = len(self._keyframes)

        # Find sorted insertion index
        idx = n_before
        for i, k in enumerate(self._keyframes):
            if t < k.time:
                idx = i
                break

        self._keyframes.insert(idx, kf)
        n_after = len(self._keyframes)

        if n_before == 0:
            pass  # no segments needed yet
        elif n_before == 1:
            # Now 2 keyframes → exactly 1 segment
            self._segments.append(Segment())
        else:
            if idx == 0:
                self._segments.insert(0, Segment())
            elif idx == n_after - 1:
                self._segments.append(Segment())
            else:
                # Split the segment that previously spanned [idx-1, idx]
                self._segments[idx - 1] = Segment()
                self._segments.insert(idx, Segment())

    def remove_keyframe(self, index: int):
        """Remove keyframe at index, merging adjacent segments."""
        if not (0 <= index < len(self._keyframes)):
            return
        self._keyframes.pop(index)
        n = len(self._keyframes)
        if n <= 1:
            self._segments.clear()
        elif index == 0:
            self._segments.pop(0)
        elif index >= len(self._segments):
            self._segments.pop(-1)
        else:
            # Keep the earlier segment, drop the later one
            self._segments.pop(index)

    def move_keyframe(self, index: int, t: float, x: float, y: float, z: float):
        """Update keyframe and re-sort. Segments follow positional order."""
        if not (0 <= index < len(self._keyframes)):
            return
        segs_backup = list(self._segments)
        self._keyframes[index] = Keyframe(time=t, x=x, y=y, z=z)
        self._keyframes.sort(key=lambda k: k.time)
        # Rebuild segments with same count, reusing backup values in order
        n_segs = max(0, len(self._keyframes) - 1)
        self._segments = [
            segs_backup[i] if i < len(segs_backup) else Segment()
            for i in range(n_segs)
        ]

    def set_segment_motion(self, seg_idx: int, motion_type: MotionType,
                           custom_bezier: Optional[List] = None):
        """Set motion type (and optional custom curve) for a segment."""
        if 0 <= seg_idx < len(self._segments):
            self._segments[seg_idx].motion_type = motion_type
            if custom_bezier is not None:
                self._segments[seg_idx].custom_bezier = list(custom_bezier)

    # ── Recording ───────────────────────────────────────────────────

    def record_frame(self, t: float, x: float, y: float, z: float):
        """Append a raw recording sample (no sorting, no segment management)."""
        self._keyframes.append(Keyframe(time=t, x=x, y=y, z=z))

    def finish_recording(self, tolerance: float = 0.04):
        """
        Simplify recorded keyframes via Ramer-Douglas-Peucker decimation.
        Rebuilds segment list with all-Linear motion.
        """
        kfs = self._keyframes
        if len(kfs) < 3:
            self._rebuild_segments_linear()
            return

        # Sort first (recording should be in order, but be safe)
        kfs.sort(key=lambda k: k.time)

        indices = self._rdp(kfs, tolerance)
        self._keyframes = [kfs[i] for i in sorted(set(indices))]
        self._rebuild_segments_linear()

    @staticmethod
    def _rdp(points: List[Keyframe], eps: float) -> List[int]:
        """Ramer-Douglas-Peucker: returns indices of kept points."""
        if len(points) <= 2:
            return list(range(len(points)))

        start = np.array([points[0].x, points[0].y, points[0].z])
        end   = np.array([points[-1].x, points[-1].y, points[-1].z])
        line_vec = end - start
        line_len = np.linalg.norm(line_vec)

        max_dist = 0.0
        max_idx  = 1
        for i in range(1, len(points) - 1):
            pt = np.array([points[i].x, points[i].y, points[i].z])
            if line_len > 1e-9:
                t = np.dot(pt - start, line_vec) / (line_len ** 2)
                t = max(0.0, min(1.0, t))
                proj = start + t * line_vec
                dist = np.linalg.norm(pt - proj)
            else:
                dist = np.linalg.norm(pt - start)
            if dist > max_dist:
                max_dist = dist
                max_idx  = i

        if max_dist > eps:
            left  = Trajectory._rdp(points[:max_idx + 1], eps)
            right = Trajectory._rdp(points[max_idx:], eps)
            return left[:-1] + [max_idx + j for j in right]
        else:
            return [0, len(points) - 1]

    def _rebuild_segments_linear(self):
        n = len(self._keyframes)
        self._segments = [Segment() for _ in range(max(0, n - 1))]

    # ── Interpolation ───────────────────────────────────────────────

    def get_position(self, t: float) -> np.ndarray:
        kfs = self._keyframes
        if not kfs:
            return np.zeros(3)
        if len(kfs) == 1:
            return np.array([kfs[0].x, kfs[0].y, kfs[0].z])

        # Clamp to valid time range
        t = max(kfs[0].time, min(t, kfs[-1].time))

        # Find enclosing segment
        seg_idx = len(kfs) - 2
        for i in range(len(kfs) - 1):
            if kfs[i].time <= t <= kfs[i + 1].time:
                seg_idx = i
                break

        a = kfs[seg_idx]
        b = kfs[seg_idx + 1]
        dt = b.time - a.time
        if dt < 1e-9:
            return np.array([b.x, b.y, b.z])

        local_t = (t - a.time) / dt
        seg = self._segments[seg_idx] if seg_idx < len(self._segments) else Segment()

        if seg.motion_type == MotionType.ORBIT:
            # Circular arc in the XY plane centered between a and b
            cx = (a.x + b.x) / 2.0
            cy = (a.y + b.y) / 2.0
            dx = b.x - a.x
            dy = b.y - a.y
            radius = max(math.sqrt(dx * dx + dy * dy) / 2.0, 0.1)
            start_angle = math.atan2(a.y - cy, a.x - cx)
            angle = start_angle + 2.0 * math.pi * local_t
            x = cx + radius * math.cos(angle)
            y = cy + radius * math.sin(angle)
            z = a.z + (b.z - a.z) * local_t
            return np.array([x, y, z])
        else:
            p = seg.apply_easing(local_t)
            return np.array([
                a.x + (b.x - a.x) * p,
                a.y + (b.y - a.y) * p,
                a.z + (b.z - a.z) * p,
            ])

    def get_curve_points(self, num_points: int = 300) -> Optional[np.ndarray]:
        """Sample trajectory at evenly-spaced times."""
        if len(self._keyframes) < 2:
            return None
        t_start = self._keyframes[0].time
        t_end   = self._keyframes[-1].time
        if t_end <= t_start:
            return None
        times = np.linspace(t_start, t_end, num_points)
        return np.array([self.get_position(tt) for tt in times])

    def clear(self):
        self._keyframes.clear()
        self._segments.clear()

    # ── Serialization ───────────────────────────────────────────────

    def to_list(self) -> List[List[float]]:
        return [[kf.time, kf.x, kf.y, kf.z] for kf in self._keyframes]

    @classmethod
    def from_list(cls, data: List[List[float]]) -> "Trajectory":
        traj = cls()
        for item in data:
            t, x, y, z = item
            traj._keyframes.append(Keyframe(time=float(t), x=float(x),
                                            y=float(y), z=float(z)))
        traj._keyframes.sort(key=lambda k: k.time)
        traj._rebuild_segments_linear()
        return traj
