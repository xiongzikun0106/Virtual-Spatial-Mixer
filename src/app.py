"""
MainWindow – Virtual Spatial Mixer application entry point.

Coordinate convention (internal)
---------------------------------
    pos[0]  = ix   X  left(−) / right(+)
    pos[1]  = iy   internal Y = user Z   front(+) / back(−)
    pos[2]  = iz   internal Z = user Y   height

Recording workflow (R-key)
--------------------------
1. User enables "● REC" on one or more tracks.
2. User presses and HOLDS the R key:
   → Playback starts automatically (if not already playing).
   → All REC-active tracks enter recording state.
   → Position is sampled at ~60 Hz from the current _positions[tid] array.
3. User releases R:
   → Sampling stops.
   → Trajectory is simplified (RDP decimation).
   → Keyframes and segments are written to the timeline.

Manual keyframe workflow
------------------------
1. Seek to desired time (click ruler / drag playhead).
2. Adjust position via left-panel X/Z/Y spinboxes or drag sphere in 3D viewport.
3. Press "+KF" or double-click timeline row → keyframe stamped.

Segment motion type editing
----------------------------
Click on the colored line between two adjacent keyframe diamonds in the timeline
→ MotionTypeDialog opens for that segment.

Single data structure
---------------------
All keyframes – whether from manual editing or R-key recording – are stored in
the same Trajectory._keyframes list.  No second keyframe system exists.
"""

import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFileDialog, QMainWindow, QMessageBox, QSplitter

from src.constants import TRACK_COLORS, UI_REFRESH_MS
from src.mixer_backend import MixerBackend, SyncTickResult
from src.scene.viewport import Viewport3D
from src.ui.theme import GLOBAL_STYLESHEET
from src.ui.timeline import TimelineWidget
from src.ui.toolbar import Toolbar
from src.ui.track_panel import TrackPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Virtual Spatial Mixer")
        self.resize(1440, 840)
        self.setStyleSheet(GLOBAL_STYLESHEET)
        self.setAcceptDrops(True)

        self._backend = MixerBackend()

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
        self.timeline.keyframe_deleted.connect(self._on_keyframe_deleted)
        self.timeline.keyframes_cleared.connect(self._on_keyframes_cleared)
        self.timeline.keyframe_selected.connect(self._on_keyframe_selected)
        self.timeline.interval_clicked.connect(self._on_interval_clicked)

    # ── Track management ─────────────────────────────────────────

    def _add_track(self, filepath: str):
        result = self._backend.add_track(filepath)
        if isinstance(result, str):
            QMessageBox.warning(self, "Import Error", result)
            return

        tid = result.tid
        color = result.color
        ix, iy, iz = result.position

        self.track_panel.add_track(tid, result.name, color)
        self.track_panel.set_track_position(tid, ix, iy, iz)
        self.viewport.add_sphere(tid, color, [ix, iy, iz])
        self._update_timeline_data()

    def _on_remove_track(self, tid: int):
        self._backend.remove_track(tid)
        self.track_panel.remove_track(tid)
        self.viewport.remove_sphere(tid)
        self._update_timeline_data()

    # ── Import ───────────────────────────────────────────────────

    def _on_import(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Import Audio",
            "",
            "Audio Files (*.wav *.flac *.ogg *.mp3);;All Files (*)",
        )
        for p in paths:
            self._add_track(p)

    # ── Transport ────────────────────────────────────────────────

    def _on_play_pause(self):
        playing = self._backend.play_pause()
        self.toolbar.set_playing(playing)
        self.track_panel.set_playing(playing)

    def _on_stop(self):
        self._backend.stop()
        self.track_panel.stop_all_recording()
        self.toolbar.set_playing(False)
        self.track_panel.set_playing(False)
        self._update_timeline_data()
        self._refresh_all_trajectories()

    def _on_seek(self, time_sec: float):
        self._backend.seek(time_sec)

    # ── Solo / Mute / Priority ───────────────────────────────────

    def _on_solo(self, tid: int, value: bool):
        self._backend.set_solo(tid, value)

    def _on_mute(self, tid: int, value: bool):
        self._backend.set_mute(tid, value)

    def _on_priority(self, tid: int, value: int):
        self._backend.set_priority(tid, value)

    # ── Coordinate changes (spinboxes or 3D viewport drag) ───────

    def _on_coord_changed(self, tid: int, ix: float, iy: float, iz: float):
        self._backend.set_coord(tid, ix, iy, iz)
        self.viewport.set_sphere_position(tid, (ix, iy, iz))

    # ── Keyframe management ───────────────────────────────────────

    def _on_keyframe_requested(self, tid: int):
        self._backend.add_keyframe_button(tid)
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframe_added(self, tid: int, time_sec: float):
        self._backend.add_keyframe_at_time(tid, time_sec)
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframe_moved(self, tid: int, kf_idx: int, new_time: float):
        self._backend.move_keyframe(tid, kf_idx, new_time)
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframe_deleted(self, tid: int, kf_idx: int):
        self._backend.delete_keyframe(tid, kf_idx)
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframes_cleared(self, tid: int):
        self._backend.clear_keyframes(tid)
        self._update_timeline_data()
        self._refresh_trajectory(tid)

    def _on_keyframe_selected(self, tid: int, kf_idx: int):
        self._backend.select_keyframe(tid, kf_idx)
        traj = self._backend.get_trajectory(tid)
        if traj is not None and 0 <= kf_idx < len(traj.keyframes):
            _, x, y, z = traj.keyframes[kf_idx]
            self.track_panel.set_track_position(tid, x, y, z)
            self.viewport.set_sphere_position(tid, (x, y, z))

    # ── Segment / interval editing ────────────────────────────────

    def _on_interval_clicked(self, tid: int, seg_idx: int):
        from src.ui.motion_type_dialog import MotionTypeDialog

        traj = self._backend.get_trajectory(tid)
        if traj is None or seg_idx >= len(traj.segments):
            return
        seg = traj.segments[seg_idx]
        dlg = MotionTypeDialog(seg, parent=self)
        if dlg.exec():
            self._backend.set_segment_motion(
                tid,
                seg_idx,
                dlg.selected_motion_type,
                dlg.custom_bezier_points,
            )
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    # ── Per-track REC button ──────────────────────────────────────

    def _on_track_rec_toggled(self, tid: int, active: bool):
        self._backend.set_track_rec(tid, active)
        if not active and not self._backend.is_r_key_held():
            self._update_timeline_data()
            self._refresh_trajectory(tid)

    # ── R-key recording ───────────────────────────────────────────

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_R and not event.isAutoRepeat():
            active, began = self._backend.r_key_pressed()
            if active:
                self.track_panel.set_global_rec_active(True)
            if began:
                self.toolbar.set_playing(True)
                self.track_panel.set_playing(True)
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_R and not event.isAutoRepeat():
            self._backend.r_key_released()
            self.track_panel.set_global_rec_active(False)
            self._update_timeline_data()
            self._refresh_all_trajectories()
        super().keyReleaseEvent(event)

    # ── Sync timer (~60 fps) ──────────────────────────────────────

    def _apply_sync_tick_result(self, res: SyncTickResult) -> None:
        self.toolbar.set_time(res.time_sec)
        self.timeline.set_playhead(res.time_sec)

        if res.drag_update is not None:
            drag_tid, ix, iy, iz = res.drag_update
            self.track_panel.set_track_position(drag_tid, ix, iy, iz)

        if not res.playing:
            return

        for tid, pos in res.sphere_positions.items():
            self.viewport.set_sphere_position(tid, pos)
            ix, iy, iz = pos
            self.track_panel.set_track_position(tid, ix, iy, iz)

        for tid, glow in res.sphere_glows.items():
            if tid in self.viewport.spheres:
                self.viewport.spheres[tid].set_glow(glow)

    def _on_sync_tick(self):
        drag_result = self.viewport.poll_drag()
        res = self._backend.sync_tick(drag_result)
        self._apply_sync_tick_result(res)

    # ── Timeline data sync ───────────────────────────────────────

    def _update_timeline_data(self):
        data = self._backend.build_timeline_tracks()
        self.timeline.set_tracks(data)
        dur = self._backend.get_max_duration()
        self.timeline.set_duration(max(dur, 10.0))

    def _refresh_trajectory(self, tid: int):
        traj = self._backend.get_trajectory(tid)
        if traj is None:
            return
        color = TRACK_COLORS[tid % len(TRACK_COLORS)]
        pts = traj.get_curve_points()
        self.viewport.update_trajectory(tid, pts, color)

    def _refresh_all_trajectories(self):
        for tid in self._backend.track_ids():
            self._refresh_trajectory(tid)

    # ── Export ───────────────────────────────────────────────────

    def _on_export(self):
        if not self._backend.track_ids():
            QMessageBox.information(self, "Export", "No tracks to export.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Mix",
            "mix_output.wav",
            "WAV Files (*.wav);;All Files (*)",
        )
        if not path:
            return
        try:
            self._backend.export_to_path(path)
            QMessageBox.information(self, "Export", f"Exported to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    # ── Drag and drop ────────────────────────────────────────────

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
        self._backend.shutdown()
        super().closeEvent(event)
