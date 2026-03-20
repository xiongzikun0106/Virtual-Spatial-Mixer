"""
MainWindow – Virtual Spatial Mixer application entry point.

Coordinate convention (internal)
---------------------------------
    pos[0]  = ix   X  left(−) / right(+)
    pos[1]  = iy   internal Y = user Z   front(+) / back(−)
    pos[2]  = iz   internal Z = user Y   height

Recording workflow
------------------
1. Keyframe mode  : user presses "+KF" or double-clicks timeline row
                    → adds a single keyframe at current playback time with current position
2. Recording mode : user enables "● REC" on a track and presses Play
                    → dragging the SpatialPad (or the coordinate spinboxes) continuously
                      records a dense position trace that is later simplified into keyframes
3. Playback       : the trajectory spline drives sphere position frame-accurately via the
                    audio callback; UI is refreshed at ~60 fps by a sync timer

Audio-UI sync guarantee
------------------------
  • The audio-thread callback reads `_positions[tid]` (np.ndarray) via
    `_audio_param_callback`.  The sync timer writes positions from the spline.
  • During recording the audio callback reads from `_positions[tid]` which is
    updated in the main thread via position_changed → _on_coord_changed.
    numpy scalar assignment is GIL-safe for our use case.
"""

import os
import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer

from src.ui.theme import GLOBAL_STYLESHEET
from src.ui.toolbar import Toolbar
from src.ui.track_panel import TrackPanel
from src.ui.timeline import TimelineWidget
from src.scene.viewport import Viewport3D
from src.audio.engine import AudioEngine
from src.audio.track import TrackBuffer
from src.audio.exporter import export_mix
from src.core.spatial_mapper import SpatialMapper
from src.core.collision import CollisionResolver
from src.core.trajectory import Trajectory
from src.constants import (
    TRACK_COLORS, DEFAULT_POSITIONS, SAMPLE_RATE, UI_REFRESH_MS,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Virtual Spatial Mixer")
        self.resize(1440, 840)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.setAcceptDrops(True)

        self._next_track_id = 0
        self._track_buffers: dict[int, TrackBuffer] = {}
        self._trajectories: dict[int, Trajectory] = {}
        self._positions: dict[int, np.ndarray] = {}

        # Track IDs currently in recording mode (REC button active)
        self._rec_tracks: set[int] = set()

        self.spatial_mapper = SpatialMapper()
        self.collision_resolver = CollisionResolver()
        self.audio_engine = AudioEngine()
        self.audio_engine.set_param_callback(self._audio_param_callback)

        self._build_ui()
        self._connect_signals()

        self._sync_timer = QTimer(self)
        self._sync_timer.setInterval(UI_REFRESH_MS)
        self._sync_timer.timeout.connect(self._on_sync_tick)
        self._sync_timer.start()

    # ── UI construction ───────────────────────────────────────────

    def _build_ui(self):
        self.toolbar = Toolbar()
        self.addToolBar(self.toolbar)

        self.track_panel = TrackPanel()
        self.viewport = Viewport3D()
        self.timeline = TimelineWidget()

        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.addWidget(self.track_panel)
        h_splitter.addWidget(self.viewport)
        h_splitter.setStretchFactor(0, 0)
        h_splitter.setStretchFactor(1, 1)

        v_splitter = QSplitter(Qt.Orientation.Vertical)
        v_splitter.addWidget(h_splitter)
        v_splitter.addWidget(self.timeline)
        v_splitter.setStretchFactor(0, 1)
        v_splitter.setStretchFactor(1, 0)

        self.setCentralWidget(v_splitter)

    def _connect_signals(self):
        # Toolbar
        self.toolbar.import_clicked.connect(self._on_import)
        self.toolbar.play_clicked.connect(self._on_play_pause)
        self.toolbar.stop_clicked.connect(self._on_stop)
        self.toolbar.export_clicked.connect(self._on_export)

        # Track panel
        self.track_panel.solo_toggled.connect(self._on_solo)
        self.track_panel.mute_toggled.connect(self._on_mute)
        self.track_panel.priority_changed.connect(self._on_priority)
        self.track_panel.remove_clicked.connect(self._on_remove_track)
        self.track_panel.coord_changed.connect(self._on_coord_changed)
        self.track_panel.keyframe_requested.connect(self._on_keyframe_requested)
        self.track_panel.rec_toggled.connect(self._on_track_rec_toggled)

        # Timeline
        self.timeline.seek_requested.connect(self._on_seek)
        self.timeline.keyframe_added.connect(self._on_keyframe_added)
        self.timeline.keyframe_moved.connect(self._on_keyframe_moved)
        self.timeline.keyframe_deleted.connect(self._on_keyframe_deleted)
        self.timeline.keyframes_cleared.connect(self._on_keyframes_cleared)
        self.timeline.keyframe_selected.connect(self._on_keyframe_selected)

    # ── Track management ─────────────────────────────────────────

    def _add_track(self, filepath: str):
        tid = self._next_track_id
        self._next_track_id += 1
        color = TRACK_COLORS[tid % len(TRACK_COLORS)]
        default_pos = DEFAULT_POSITIONS[tid % len(DEFAULT_POSITIONS)]

        try:
            buf = TrackBuffer(filepath, tid)
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        buf.priority = 0
        self._track_buffers[tid] = buf
        self._trajectories[tid] = Trajectory()
        self._positions[tid] = np.array(default_pos, dtype=np.float64)

        self.audio_engine.add_track(buf)
        self.track_panel.add_track(tid, buf.name, color)
        self.track_panel.set_track_position(tid, *default_pos)
        self.viewport.add_sphere(tid, color, default_pos)
        self._update_timeline_data()

    def _on_remove_track(self, tid: int):
        if tid in self._track_buffers:
            buf = self._track_buffers.pop(tid)
            self.audio_engine.remove_track(buf)
        self._trajectories.pop(tid, None)
        self._positions.pop(tid, None)
        self._rec_tracks.discard(tid)
        self.track_panel.remove_track(tid)
        self.viewport.remove_sphere(tid)
        self._update_timeline_data()

    # ── Import ───────────────────────────────────────────────────

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import Audio", "",
            "Audio Files (*.wav *.flac *.ogg *.mp3);;All Files (*)"
        )
        for p in paths:
            self._add_track(p)

    # ── Transport ────────────────────────────────────────────────

    def _on_play_pause(self):
        if self.audio_engine.playing:
            self.audio_engine.pause()
            self.toolbar.set_playing(False)
            self.track_panel.set_playing(False)
        else:
            self.audio_engine.play()
            self.toolbar.set_playing(True)
            self.track_panel.set_playing(True)

    def _on_stop(self):
        # Deactivate all REC buttons first (each fires rec_toggled → finish_recording)
        self.track_panel.stop_all_recording()

        self.audio_engine.stop()
        self.toolbar.set_playing(False)
        self.track_panel.set_playing(False)

        self._update_timeline_data()
        self._refresh_all_trajectories()

    def _on_seek(self, time_sec: float):
        frame = int(time_sec * SAMPLE_RATE)
        self.audio_engine.seek(frame)

    # ── Solo / Mute / Priority ───────────────────────────────────

    def _on_solo(self, tid: int, value: bool):
        if tid in self._track_buffers:
            self._track_buffers[tid].solo = value

    def _on_mute(self, tid: int, value: bool):
        if tid in self._track_buffers:
            self._track_buffers[tid].muted = value

    def _on_priority(self, tid: int, value: int):
        if tid in self._track_buffers:
            self._track_buffers[tid].priority = value

    # ── Coordinate changes (spinbox or SpatialPad drag) ──────────

    def _on_coord_changed(self, tid: int, ix: float, iy: float, iz: float):
        """Update sphere position and optionally record trajectory frame."""
        pos = np.array([ix, iy, iz], dtype=np.float64)
        self._positions[tid] = pos
        self.viewport.set_sphere_position(tid, (ix, iy, iz))

        # Only record trajectory when REC is active AND playback is running.
        # This prevents accidental trajectory writes when merely adjusting position.
        if tid in self._rec_tracks and self.audio_engine.playing:
            t = self.audio_engine.get_time()
            self._trajectories[tid].record_frame(t, ix, iy, iz)

    # ── Keyframe management ───────────────────────────────────────

    def _on_keyframe_requested(self, tid: int):
        """+KF button: stamp current position at current playback time."""
        traj = self._trajectories.get(tid)
        pos  = self._positions.get(tid)
        if traj is None or pos is None:
            return
        t = self.audio_engine.get_time()
        traj.add_keyframe(t, float(pos[0]), float(pos[1]), float(pos[2]))
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframe_added(self, tid: int, time_sec: float):
        """Double-click in timeline row: add keyframe at clicked time."""
        traj = self._trajectories.get(tid)
        pos  = self._positions.get(tid)
        if traj is not None and pos is not None:
            traj.add_keyframe(time_sec, float(pos[0]), float(pos[1]), float(pos[2]))
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    def _on_keyframe_moved(self, tid: int, kf_idx: int, new_time: float):
        """Drag keyframe diamond in timeline."""
        traj = self._trajectories.get(tid)
        if traj is not None and 0 <= kf_idx < len(traj.keyframes):
            _, x, y, z = traj.keyframes[kf_idx]
            traj.move_keyframe(kf_idx, new_time, x, y, z)
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    def _on_keyframe_deleted(self, tid: int, kf_idx: int):
        """Delete a single keyframe (right-click → Delete)."""
        traj = self._trajectories.get(tid)
        if traj is not None and 0 <= kf_idx < len(traj.keyframes):
            traj.remove_keyframe(kf_idx)
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    def _on_keyframes_cleared(self, tid: int):
        """Clear all keyframes for a track (right-click → Clear All)."""
        traj = self._trajectories.get(tid)
        if traj is not None:
            traj.clear()
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    def _on_keyframe_selected(self, tid: int, kf_idx: int):
        """
        User clicked a keyframe diamond in the timeline.
        Show the keyframe's position in the TrackPanel (seek already done by timeline).
        """
        traj = self._trajectories.get(tid)
        if traj is not None and 0 <= kf_idx < len(traj.keyframes):
            _, x, y, z = traj.keyframes[kf_idx]
            self.track_panel.set_track_position(tid, x, y, z)
            self._positions[tid] = np.array([x, y, z], dtype=np.float64)
            self.viewport.set_sphere_position(tid, (x, y, z))

    # ── Per-track recording toggle ────────────────────────────────

    def _on_track_rec_toggled(self, tid: int, active: bool):
        if active:
            self._rec_tracks.add(tid)
        else:
            self._rec_tracks.discard(tid)
            traj = self._trajectories.get(tid)
            if traj:
                traj.finish_recording()
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    # ── Audio parameter callback (audio thread) ───────────────────

    def _audio_param_callback(self, track: TrackBuffer, frame: int):
        """
        Called from the sounddevice audio thread for every block.
        Must be fast and non-blocking.

        Returns (gain, pan, cutoff) computed from the track's current position.
        During recording the position is whatever the user dragged to last;
        during normal playback it is driven by the trajectory spline.
        """
        tid = track.track_id
        t   = frame / SAMPLE_RATE

        traj = self._trajectories.get(tid)
        if traj and len(traj.keyframes) >= 2 and tid not in self._rec_tracks:
            # Spline-driven position (frame-accurate)
            pos = traj.get_position(t)
        else:
            pos = self._positions.get(tid, np.zeros(3))

        gain, pan, cutoff = self.spatial_mapper.compute(pos)
        return gain, pan, cutoff

    # ── Sync timer (~60 fps) ──────────────────────────────────────

    def _on_sync_tick(self):
        t = self.audio_engine.get_time()
        self.toolbar.set_time(t)
        self.timeline.set_playhead(t)

        if not self.audio_engine.playing:
            return

        self._resolve_collisions()

        # Advance trajectory-driven positions for non-recording tracks
        for tid, traj in self._trajectories.items():
            if tid in self._rec_tracks:
                continue   # position is already live from SpatialPad drag
            if traj.keyframes and len(traj.keyframes) >= 2:
                pos = traj.get_position(t)
                self._positions[tid] = pos
                px, py, pz = float(pos[0]), float(pos[1]), float(pos[2])
                self.viewport.set_sphere_position(tid, (px, py, pz))
                self.track_panel.set_track_position(tid, px, py, pz)

        # Glow brightness from gain
        for tid, pos in self._positions.items():
            if tid in self.viewport.spheres:
                gain, _, _ = self.spatial_mapper.compute(pos)
                self.viewport.spheres[tid].set_glow(gain)

    # ── Collision resolver ────────────────────────────────────────

    def _resolve_collisions(self):
        twp = [
            (tid, buf.priority, self._positions.get(tid, np.zeros(3)))
            for tid, buf in self._track_buffers.items()
        ]
        duck_gains = self.collision_resolver.resolve(twp)
        for tid, dg in duck_gains.items():
            if tid in self._track_buffers:
                self._track_buffers[tid].duck_gain = dg

    # ── Timeline / SpatialPad data sync ──────────────────────────

    def _update_timeline_data(self):
        data = []
        for tid, buf in self._track_buffers.items():
            color = TRACK_COLORS[tid % len(TRACK_COLORS)]
            traj  = self._trajectories.get(tid)
            data.append({
                "id":             tid,
                "name":           buf.name,
                "color":          color,
                "waveform":       buf.get_waveform_overview(),
                "keyframes":      traj.keyframes if traj else [],
                "track_duration": buf.duration,
            })
        self.timeline.set_tracks(data)
        dur = self.audio_engine.get_max_duration()
        self.timeline.set_duration(max(dur, 10.0))

    def _refresh_trajectory(self, tid: int):
        """Update both the 3D viewport trajectory and the SpatialPad motion path."""
        traj = self._trajectories.get(tid)
        if traj is None:
            return
        color = TRACK_COLORS[tid % len(TRACK_COLORS)]
        pts = traj.get_curve_points()
        # 3D viewport
        self.viewport.update_trajectory(tid, pts, color)
        # SpatialPad (2D overlay in track panel)
        self.track_panel.update_track_trajectory(tid, pts, traj.keyframes)

    def _refresh_all_trajectories(self):
        for tid in self._trajectories:
            self._refresh_trajectory(tid)

    # ── Export ───────────────────────────────────────────────────

    def _on_export(self):
        if not self._track_buffers:
            QMessageBox.information(self, "Export", "No tracks to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Mix", "mix_output.wav",
            "WAV Files (*.wav);;All Files (*)"
        )
        if not path:
            return
        try:
            export_mix(
                list(self._track_buffers.values()),
                self._trajectories,
                self.spatial_mapper,
                self.collision_resolver,
                path,
            )
            QMessageBox.information(self, "Export", f"Exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Drag and Drop ────────────────────────────────────────────

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path and os.path.isfile(path):
                if os.path.splitext(path)[1].lower() in (".wav", ".flac", ".ogg", ".mp3"):
                    self._add_track(path)

    # ── Cleanup ──────────────────────────────────────────────────

    def closeEvent(self, event):
        self._sync_timer.stop()
        self.audio_engine.shutdown()
        super().closeEvent(event)
