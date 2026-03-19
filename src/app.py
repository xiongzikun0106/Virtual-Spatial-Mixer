import os
import numpy as np
from PyQt6.QtWidgets import (
    QMainWindow, QSplitter, QFileDialog, QMessageBox, QApplication,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QCursor

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
    TRACK_COLORS, DEFAULT_POSITIONS, SAMPLE_RATE,
    UI_REFRESH_MS,
)

# Pixels of cursor travel that equal 1 world unit during recording
_REC_SENSITIVITY = 0.02


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Virtual Spatial Mixer")
        self.resize(1400, 800)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.setAcceptDrops(True)

        self._next_track_id = 0
        self._track_buffers: dict[int, TrackBuffer] = {}
        self._trajectories: dict[int, Trajectory] = {}
        self._positions: dict[int, np.ndarray] = {}

        # Set of track IDs currently in per-track recording mode
        self._rec_tracks: set[int] = set()
        # Last cursor position for computing mouse deltas during recording
        self._last_cursor_pos = QCursor.pos()

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
        self.toolbar.import_clicked.connect(self._on_import)
        self.toolbar.play_clicked.connect(self._on_play_pause)
        self.toolbar.stop_clicked.connect(self._on_stop)
        self.toolbar.export_clicked.connect(self._on_export)

        self.track_panel.solo_toggled.connect(self._on_solo)
        self.track_panel.mute_toggled.connect(self._on_mute)
        self.track_panel.priority_changed.connect(self._on_priority)
        self.track_panel.remove_clicked.connect(self._on_remove_track)
        self.track_panel.coord_changed.connect(self._on_coord_changed)
        self.track_panel.keyframe_requested.connect(self._on_keyframe_requested)
        self.track_panel.rec_toggled.connect(self._on_track_rec_toggled)

        self.timeline.seek_requested.connect(self._on_seek)
        self.timeline.keyframe_added.connect(self._on_keyframe_added)
        self.timeline.keyframe_moved.connect(self._on_keyframe_moved)

    # ── Track management ─────────────────────────────────────────

    def _add_track(self, filepath: str):
        tid = self._next_track_id
        self._next_track_id += 1
        color_idx = tid % len(TRACK_COLORS)
        color = TRACK_COLORS[color_idx]
        pos_idx = tid % len(DEFAULT_POSITIONS)
        default_pos = DEFAULT_POSITIONS[pos_idx]

        try:
            buf = TrackBuffer(filepath, tid)
        except Exception as e:
            QMessageBox.warning(self, "Import Error", str(e))
            return

        self._track_buffers[tid] = buf
        self._trajectories[tid] = Trajectory()
        self._positions[tid] = np.array(default_pos, dtype=np.float64)

        buf.priority = 0
        self.audio_engine.add_track(buf)

        self.track_panel.add_track(tid, buf.name, color)
        # Initialise spinboxes with the default position
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

    # ── Transport controls ───────────────────────────────────────

    def _on_play_pause(self):
        if self.audio_engine.playing:
            self.audio_engine.pause()
            self.toolbar.set_playing(False)
        else:
            self.audio_engine.play()
            self.toolbar.set_playing(True)
            # Reset cursor baseline so recording doesn't jump on first frame
            self._last_cursor_pos = QCursor.pos()

    def _on_stop(self):
        # Deactivate all per-track rec buttons first (each fires rec_toggled → finish_recording)
        self.track_panel.stop_all_recording()

        self.audio_engine.stop()
        self.toolbar.set_playing(False)

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

    # ── Coordinate control (from TrackPanel spinboxes) ───────────

    def _on_coord_changed(self, tid: int, ix: float, iy: float, iz: float):
        """User edited a coordinate spinbox → update sphere and audio immediately."""
        pos = np.array([ix, iy, iz], dtype=np.float64)
        self._positions[tid] = pos
        self.viewport.set_sphere_position(tid, (ix, iy, iz))

        # During playback, write a continuous recording frame
        if self.audio_engine.playing:
            t = self.audio_engine.get_time()
            self._trajectories[tid].record_frame(t, ix, iy, iz)

    # ── Keyframe from TrackPanel button ──────────────────────────

    def _on_keyframe_requested(self, tid: int):
        """'+ KF' button pressed: stamp current position at current playback time."""
        traj = self._trajectories.get(tid)
        pos  = self._positions.get(tid)
        if traj is None or pos is None:
            return
        t = self.audio_engine.get_time()
        traj.add_keyframe(t, float(pos[0]), float(pos[1]), float(pos[2]))
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    # ── Per-track recording toggle ────────────────────────────────

    def _on_track_rec_toggled(self, tid: int, active: bool):
        if active:
            self._rec_tracks.add(tid)
            # Reset cursor baseline to avoid a jump on first captured frame
            self._last_cursor_pos = QCursor.pos()
        else:
            self._rec_tracks.discard(tid)
            traj = self._trajectories.get(tid)
            if traj:
                traj.finish_recording()
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    # ── Keyframe editing from timeline ───────────────────────────

    def _on_keyframe_added(self, tid: int, time_sec: float):
        traj = self._trajectories.get(tid)
        pos  = self._positions.get(tid)
        if traj is not None and pos is not None:
            traj.add_keyframe(time_sec, float(pos[0]), float(pos[1]), float(pos[2]))
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    def _on_keyframe_moved(self, tid: int, kf_idx: int, new_time: float):
        traj = self._trajectories.get(tid)
        if traj is not None and 0 <= kf_idx < len(traj.keyframes):
            _, x, y, z = traj.keyframes[kf_idx]
            traj.move_keyframe(kf_idx, new_time, x, y, z)
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    # ── Audio parameter callback (called from audio thread) ──────

    def _audio_param_callback(self, track: TrackBuffer, frame: int):
        tid = track.track_id
        t   = frame / SAMPLE_RATE

        traj = self._trajectories.get(tid)
        if traj and traj.keyframes and len(traj.keyframes) >= 2:
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

        if self.audio_engine.playing:
            self._resolve_collisions()

            # Mouse-capture recording for active rec tracks
            if self._rec_tracks:
                self._handle_recording_mouse(t)

            # Advance trajectory-driven positions (skip tracks under live control)
            for tid, traj in self._trajectories.items():
                if tid in self._rec_tracks:
                    continue  # position driven by mouse capture, not trajectory
                if traj.keyframes and len(traj.keyframes) >= 2:
                    pos = traj.get_position(t)
                    self._positions[tid] = pos
                    self.viewport.set_sphere_position(tid, tuple(pos))
                    self.track_panel.set_track_position(
                        tid, float(pos[0]), float(pos[1]), float(pos[2])
                    )

            # Glow brightness tied to gain
            for tid in self._positions:
                if tid in self.viewport.spheres:
                    gain, _, _ = self.spatial_mapper.compute(self._positions[tid])
                    self.viewport.spheres[tid].set_glow(gain)

    def _handle_recording_mouse(self, t: float):
        """Translate global cursor delta into position changes for recording tracks."""
        cursor_pos = QCursor.pos()
        dx = cursor_pos.x() - self._last_cursor_pos.x()
        dy = cursor_pos.y() - self._last_cursor_pos.y()
        self._last_cursor_pos = cursor_pos

        if dx == 0 and dy == 0:
            return

        for tid in list(self._rec_tracks):
            if tid not in self._positions:
                continue
            pos = self._positions[tid].copy()
            pos[0] = float(np.clip(pos[0] + dx * _REC_SENSITIVITY, -20, 20))  # X left/right
            pos[1] = float(np.clip(pos[1] - dy * _REC_SENSITIVITY, -20, 20))  # internal Y = user Z
            self._positions[tid] = pos
            self.viewport.set_sphere_position(tid, tuple(pos))
            self.track_panel.set_track_position(tid, pos[0], pos[1], pos[2])
            self._trajectories[tid].record_frame(t, pos[0], pos[1], pos[2])

    def _resolve_collisions(self):
        twp = []
        for tid, buf in self._track_buffers.items():
            pos = self._positions.get(tid, np.zeros(3))
            twp.append((tid, buf.priority, pos))
        duck_gains = self.collision_resolver.resolve(twp)
        for tid, dg in duck_gains.items():
            if tid in self._track_buffers:
                self._track_buffers[tid].duck_gain = dg

    # ── Timeline data sync ───────────────────────────────────────

    def _update_timeline_data(self):
        data = []
        for tid, buf in self._track_buffers.items():
            color_idx = tid % len(TRACK_COLORS)
            traj = self._trajectories.get(tid)
            data.append({
                "id": tid,
                "name": buf.name,
                "color": TRACK_COLORS[color_idx],
                "waveform": buf.get_waveform_overview(),
                "keyframes": traj.keyframes if traj else [],
                "track_duration": buf.duration,
            })
        self.timeline.set_tracks(data)
        dur = self.audio_engine.get_max_duration()
        self.timeline.set_duration(dur if dur > 0 else 10.0)

    def _refresh_trajectory(self, tid: int):
        traj = self._trajectories.get(tid)
        color_idx = tid % len(TRACK_COLORS)
        color = TRACK_COLORS[color_idx]
        if traj:
            pts = traj.get_curve_points()
            self.viewport.update_trajectory(tid, pts, color)

    def _refresh_all_trajectories(self):
        for tid in self._trajectories:
            self._refresh_trajectory(tid)

    # ── Export ────────────────────────────────────────────────────

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

        tracks = list(self._track_buffers.values())
        try:
            export_mix(
                tracks,
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
                ext = os.path.splitext(path)[1].lower()
                if ext in (".wav", ".flac", ".ogg", ".mp3"):
                    self._add_track(path)

    # ── Cleanup ──────────────────────────────────────────────────

    def closeEvent(self, event):
        self._sync_timer.stop()
        self.audio_engine.shutdown()
        super().closeEvent(event)
