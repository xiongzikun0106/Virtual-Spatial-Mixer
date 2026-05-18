"""
Headless mixer state + audio logic shared by PyQt UI and webview UI.

All public methods are guarded by a re-entrant lock so the sounddevice
callback can safely read trajectories/positions together with the UI thread.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from src.audio.engine import AudioEngine
from src.audio.exporter import export_mix
from src.audio.track import TrackBuffer
from src.constants import DEFAULT_POSITIONS, SAMPLE_RATE, TRACK_COLORS
from src.core.collision import CollisionResolver
from src.core.spatial_mapper import SpatialMapper
from src.core.trajectory import MotionType, Trajectory


@dataclass
class TrackAdded:
    tid: int
    name: str
    color: tuple[float, float, float]
    position: tuple[float, float, float]


@dataclass
class SyncTickResult:
    time_sec: float
    playing: bool
    drag_update: Optional[tuple[int, float, float, float]] = None
    sphere_positions: dict[int, tuple[float, float, float]] = field(default_factory=dict)
    sphere_glows: dict[int, float] = field(default_factory=dict)


class MixerBackend:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._next_track_id = 0
        self._track_buffers: dict[int, TrackBuffer] = {}
        self._trajectories: dict[int, Trajectory] = {}
        self._positions: dict[int, np.ndarray] = {}
        self._rec_tracks: set[int] = set()
        self._r_key_held = False

        self.spatial_mapper = SpatialMapper()
        self.collision_resolver = CollisionResolver()
        self.audio_engine = AudioEngine()
        self.audio_engine.set_param_callback(self._audio_param_callback)

    # ── lifecycle ─────────────────────────────────────────────────

    def shutdown(self) -> None:
        with self._lock:
            self.audio_engine.shutdown()

    def get_trajectory(self, tid: int) -> Optional[Trajectory]:
        with self._lock:
            return self._trajectories.get(tid)

    # ── tracks ────────────────────────────────────────────────────

    def add_track(self, filepath: str) -> TrackAdded | str:
        with self._lock:
            tid = self._next_track_id
            color = TRACK_COLORS[tid % len(TRACK_COLORS)]
            default_pos = DEFAULT_POSITIONS[tid % len(DEFAULT_POSITIONS)]
            try:
                buf = TrackBuffer(filepath, tid)
            except Exception as e:
                return str(e)
            buf.priority = 0
            self._next_track_id += 1
            self._track_buffers[tid] = buf
            self._trajectories[tid] = Trajectory()
            self._positions[tid] = np.array(default_pos, dtype=np.float64)
            self.audio_engine.add_track(buf)
            pos = tuple(float(x) for x in default_pos)
            return TrackAdded(tid=tid, name=buf.name, color=color, position=pos)

    def remove_track(self, tid: int) -> None:
        with self._lock:
            if tid in self._track_buffers:
                buf = self._track_buffers.pop(tid)
                self.audio_engine.remove_track(buf)
            self._trajectories.pop(tid, None)
            self._positions.pop(tid, None)
            self._rec_tracks.discard(tid)

    # ── transport ─────────────────────────────────────────────────

    def play_pause(self) -> bool:
        with self._lock:
            if self.audio_engine.playing:
                self.audio_engine.pause()
                return False
            self.audio_engine.play()
            return True

    def stop(self) -> None:
        """Stop playback and finalize R-key recording if active."""
        with self._lock:
            if self._r_key_held:
                self._finish_r_recording_unlocked()
            self.audio_engine.stop()

    def rec_armed_track_ids(self) -> list[int]:
        with self._lock:
            return list(self._rec_tracks)

    def seek(self, time_sec: float) -> None:
        with self._lock:
            frame = int(time_sec * SAMPLE_RATE)
            self.audio_engine.seek(frame)

    def is_playing(self) -> bool:
        with self._lock:
            return self.audio_engine.playing

    def is_r_key_held(self) -> bool:
        with self._lock:
            return self._r_key_held

    def get_time(self) -> float:
        # Intentionally no lock: used for coarse UI polling; frame counter is atomic enough.
        return self.audio_engine.get_time()

    def get_max_duration(self) -> float:
        with self._lock:
            return self.audio_engine.get_max_duration()

    # ── mix / solo ────────────────────────────────────────────────

    def set_solo(self, tid: int, value: bool) -> None:
        with self._lock:
            if tid in self._track_buffers:
                self._track_buffers[tid].solo = value

    def set_mute(self, tid: int, value: bool) -> None:
        with self._lock:
            if tid in self._track_buffers:
                self._track_buffers[tid].muted = value

    def set_priority(self, tid: int, value: int) -> None:
        with self._lock:
            if tid in self._track_buffers:
                self._track_buffers[tid].priority = value

    # ── spatial ───────────────────────────────────────────────────

    def set_coord(self, tid: int, ix: float, iy: float, iz: float) -> None:
        with self._lock:
            if tid not in self._positions:
                return
            self._positions[tid] = np.array([ix, iy, iz], dtype=np.float64)

    def get_positions(self) -> dict[int, tuple[float, float, float]]:
        with self._lock:
            return {
                tid: (float(p[0]), float(p[1]), float(p[2]))
                for tid, p in self._positions.items()
            }

    def get_sphere_glows(self) -> dict[int, float]:
        with self._lock:
            return {
                tid: float(self.spatial_mapper.compute(p)[0])
                for tid, p in self._positions.items()
            }

    # ── keyframes ───────────────────────────────────────────────────

    def add_keyframe_button(self, tid: int) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            pos = self._positions.get(tid)
            if traj is None or pos is None:
                return
            t = self.audio_engine.get_time()
            traj.add_keyframe(t, float(pos[0]), float(pos[1]), float(pos[2]))

    def add_keyframe_at_time(self, tid: int, time_sec: float) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            pos = self._positions.get(tid)
            if traj is not None and pos is not None:
                traj.add_keyframe(
                    time_sec, float(pos[0]), float(pos[1]), float(pos[2])
                )

    def move_keyframe(self, tid: int, kf_idx: int, new_time: float) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            if traj is not None and 0 <= kf_idx < len(traj.keyframes):
                _, x, y, z = traj.keyframes[kf_idx]
                traj.move_keyframe(kf_idx, new_time, x, y, z)

    def delete_keyframe(self, tid: int, kf_idx: int) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            if traj is not None and 0 <= kf_idx < len(traj.keyframes):
                traj.remove_keyframe(kf_idx)

    def clear_keyframes(self, tid: int) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            if traj is not None:
                traj.clear()

    def select_keyframe(self, tid: int, kf_idx: int) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            if traj is not None and 0 <= kf_idx < len(traj.keyframes):
                _, x, y, z = traj.keyframes[kf_idx]
                self._positions[tid] = np.array([x, y, z], dtype=np.float64)

    def set_segment_motion(
        self,
        tid: int,
        seg_idx: int,
        motion_type: MotionType,
        custom_bezier: Optional[list] = None,
    ) -> None:
        with self._lock:
            traj = self._trajectories.get(tid)
            if traj is None or seg_idx >= len(traj.segments):
                return
            traj.set_segment_motion(seg_idx, motion_type, custom_bezier)

    # ── recording ───────────────────────────────────────────────────

    def set_track_rec(self, tid: int, active: bool) -> None:
        with self._lock:
            if active:
                self._rec_tracks.add(tid)
            else:
                self._rec_tracks.discard(tid)
                if not self._r_key_held:
                    traj = self._trajectories.get(tid)
                    if traj:
                        traj.finish_recording()

    def r_key_pressed(self) -> tuple[bool, bool]:
        """Return ``(rec_gate_active, playback_auto_started)``."""
        with self._lock:
            if not self._rec_tracks:
                return False, False
            self._r_key_held = True
            if not self.audio_engine.playing:
                self.audio_engine.play()
                return True, True
            return True, False

    def r_key_released(self) -> None:
        with self._lock:
            self._finish_r_recording_unlocked()

    def _finish_r_recording_unlocked(self) -> None:
        if not self._r_key_held:
            return
        self._r_key_held = False
        for tid in list(self._rec_tracks):
            traj = self._trajectories.get(tid)
            if traj:
                traj.finish_recording()

    # ── audio thread ────────────────────────────────────────────────

    def _audio_param_callback(self, track: TrackBuffer, frame: int):
        tid = track.track_id
        t = frame / SAMPLE_RATE
        with self._lock:
            traj = self._trajectories.get(tid)
            recording_active = self._r_key_held and tid in self._rec_tracks
            if traj and len(traj.keyframes) >= 2 and not recording_active:
                pos = traj.get_position(t)
            else:
                pos = self._positions.get(tid, np.zeros(3))
            gain, pan, cutoff = self.spatial_mapper.compute(pos)
        return gain, pan, cutoff

    # ── sync tick (UI thread) ───────────────────────────────────────

    def sync_tick(
        self, drag_result: Optional[tuple[int, tuple[float, float, float]]]
    ) -> SyncTickResult:
        with self._lock:
            t = self.audio_engine.get_time()
            playing = self.audio_engine.playing

            drag_update: Optional[tuple[int, float, float, float]] = None
            if drag_result is not None:
                drag_tid, drag_pos = drag_result
                ix, iy, iz = drag_pos
                self._positions[drag_tid] = np.array([ix, iy, iz], dtype=np.float64)
                drag_update = (drag_tid, ix, iy, iz)

            sphere_positions: dict[int, tuple[float, float, float]] = {}
            sphere_glows: dict[int, float] = {}

            if not playing:
                return SyncTickResult(
                    time_sec=t,
                    playing=playing,
                    drag_update=drag_update,
                    sphere_positions=sphere_positions,
                    sphere_glows=sphere_glows,
                )

            twp = [
                (tid, buf.priority, self._positions.get(tid, np.zeros(3)))
                for tid, buf in self._track_buffers.items()
            ]
            duck_gains = self.collision_resolver.resolve(twp)
            for tid, dg in duck_gains.items():
                if tid in self._track_buffers:
                    self._track_buffers[tid].duck_gain = dg

            if self._r_key_held:
                for tid in self._rec_tracks:
                    pos = self._positions.get(tid, np.zeros(3))
                    self._trajectories[tid].record_frame(
                        t, float(pos[0]), float(pos[1]), float(pos[2])
                    )

            for tid, traj in self._trajectories.items():
                if self._r_key_held and tid in self._rec_tracks:
                    continue
                if len(traj.keyframes) >= 2:
                    pos = traj.get_position(t)
                    self._positions[tid] = pos
                    px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
                    sphere_positions[tid] = (px, py, pz)

            for tid, pos in self._positions.items():
                gain, _, _ = self.spatial_mapper.compute(pos)
                sphere_glows[tid] = float(gain)

            return SyncTickResult(
                time_sec=t,
                playing=playing,
                drag_update=drag_update,
                sphere_positions=sphere_positions,
                sphere_glows=sphere_glows,
            )

    # ── timeline payload ────────────────────────────────────────────

    def build_timeline_tracks(self) -> list[dict[str, Any]]:
        with self._lock:
            data: list[dict[str, Any]] = []
            for tid, buf in self._track_buffers.items():
                color = TRACK_COLORS[tid % len(TRACK_COLORS)]
                traj = self._trajectories.get(tid)
                segs_data = []
                if traj:
                    for seg in traj.segments:
                        segs_data.append({"motion_type": seg.motion_type.value})
                wf = buf.get_waveform_overview()
                data.append(
                    {
                        "id": tid,
                        "name": buf.name,
                        "color": color,
                        "muted": buf.muted,
                        "solo": buf.solo,
                        "rec_armed": tid in self._rec_tracks,
                        "waveform": wf.astype(float).tolist(),
                        "keyframes": traj.keyframes if traj else [],
                        "segments": segs_data,
                        "track_duration": buf.duration,
                    }
                )
            return data

    def export_to_path(self, path: str) -> None:
        with self._lock:
            export_mix(
                list(self._track_buffers.values()),
                self._trajectories,
                self.spatial_mapper,
                self.collision_resolver,
                path,
            )

    def track_ids(self) -> list[int]:
        with self._lock:
            return list(self._track_buffers.keys())
