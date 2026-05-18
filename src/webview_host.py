"""
pywebview shell (方案 A): Windows 使用 Edge WebView2，其他平台使用 pywebview 的默认 GUI。

前端为 ``frontend/dist`` 下的 Vite 构建产物；开发时可另开 ``npm run dev`` 并把
``VSM_DEV_URL`` 指向 ``http://127.0.0.1:5173``（需允许 dev server CORS / 或仅用于浏览器调试）。
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

import webview

from src.constants import UI_REFRESH_MS
from src.mixer_backend import MixerBackend


def _dist_index() -> Path:
    return Path(__file__).resolve().parent.parent / "frontend" / "dist" / "index.html"


class WebviewApi:
    """暴露给 ``window.pywebview.api`` 的 JSON 可序列化接口。"""

    def __init__(self, backend: MixerBackend) -> None:
        self._b = backend

    def get_snapshot(self) -> dict:
        return {
            "transport": {
                "time": self._b.get_time(),
                "playing": self._b.is_playing(),
                "duration": max(self._b.get_max_duration(), 10.0),
            },
            "tracks": self._b.build_timeline_tracks(),
            "positions": self._b.get_positions(),
            "glows": self._b.get_sphere_glows(),
        }

    def import_audio(self) -> dict:
        win = webview.windows[0]
        paths = win.create_file_dialog(
            webview.OPEN_DIALOG,
            allow_multiple=True,
            file_types=(
                "Audio (*.wav;*.flac;*.ogg;*.mp3)",
                "All files (*.*)",
            ),
        )
        errors: list[str] = []
        if not paths:
            return {"errors": errors, "snapshot": self.get_snapshot()}
        if isinstance(paths, str):
            paths = (paths,)
        for p in paths:
            r = self._b.add_track(p)
            if isinstance(r, str):
                errors.append(f"{p}: {r}")
        return {"errors": errors, "snapshot": self.get_snapshot()}

    def export_audio(self) -> dict:
        win = webview.windows[0]
        path = win.create_file_dialog(
            webview.SAVE_DIALOG,
            directory=os.path.expanduser("~"),
            save_filename="mix_output.wav",
            file_types=("WAV (*.wav)", "All files (*.*)"),
        )
        if not path:
            return {"ok": False, "message": "cancelled", "snapshot": self.get_snapshot()}
        if isinstance(path, tuple):
            path = path[0]
        try:
            if not self._b.track_ids():
                return {"ok": False, "message": "No tracks", "snapshot": self.get_snapshot()}
            self._b.export_to_path(path)
            return {"ok": True, "message": path, "snapshot": self.get_snapshot()}
        except Exception as e:
            return {"ok": False, "message": str(e), "snapshot": self.get_snapshot()}

    def play_pause(self) -> dict:
        playing = self._b.play_pause()
        return {"playing": playing, "snapshot": self.get_snapshot()}

    def stop(self) -> dict:
        ids = self._b.rec_armed_track_ids()
        self._b.stop()
        for tid in ids:
            self._b.set_track_rec(tid, False)
        return {"snapshot": self.get_snapshot()}

    def seek(self, time_sec: float) -> dict:
        self._b.seek(float(time_sec))
        return {"snapshot": self.get_snapshot()}

    def set_mute(self, tid: int, value: bool) -> dict:
        self._b.set_mute(int(tid), bool(value))
        return {"snapshot": self.get_snapshot()}

    def set_solo(self, tid: int, value: bool) -> dict:
        self._b.set_solo(int(tid), bool(value))
        return {"snapshot": self.get_snapshot()}

    def set_priority(self, tid: int, value: int) -> dict:
        self._b.set_priority(int(tid), int(value))
        return {"snapshot": self.get_snapshot()}

    def set_coord(self, tid: int, x: float, y: float, z: float) -> dict:
        self._b.set_coord(int(tid), float(x), float(y), float(z))
        return {"snapshot": self.get_snapshot()}

    def stamp_keyframe(self, tid: int) -> dict:
        self._b.add_keyframe_button(int(tid))
        return {"snapshot": self.get_snapshot()}

    def remove_track(self, tid: int) -> dict:
        self._b.remove_track(int(tid))
        return {"snapshot": self.get_snapshot()}

    def set_track_rec(self, tid: int, active: bool) -> dict:
        self._b.set_track_rec(int(tid), bool(active))
        return {"snapshot": self.get_snapshot()}

    def r_key_down(self) -> dict:
        active, began = self._b.r_key_pressed()
        return {"active": active, "began": began, "snapshot": self.get_snapshot()}

    def r_key_up(self) -> dict:
        self._b.r_key_released()
        return {"snapshot": self.get_snapshot()}


def run_webview_app() -> None:
    dist = _dist_index()
    dev_url = os.environ.get("VSM_DEV_URL", "").strip()

    if not dev_url and not dist.is_file():
        print(
            "未找到前端构建: 请先执行\n"
            "  cd frontend && npm install && npm run build\n"
            "或设置环境变量 VSM_DEV_URL=http://127.0.0.1:5173 指向 Vite 开发服务器。",
            file=sys.stderr,
        )
        sys.exit(1)

    backend = MixerBackend()
    api = WebviewApi(backend)

    stop_tick = threading.Event()

    def _tick_loop() -> None:
        dt = UI_REFRESH_MS / 1000.0
        while not stop_tick.wait(dt):
            try:
                backend.sync_tick(None)
            except Exception:
                pass

    tick_thread = threading.Thread(target=_tick_loop, daemon=True)
    tick_thread.start()

    if dev_url:
        url = dev_url
    else:
        url = dist.resolve().as_uri()

    kwargs: dict = {
        "title": "Virtual Spatial Mixer",
        "url": url,
        "js_api": api,
        "width": 1440,
        "height": 900,
    }

    webview.create_window(**kwargs)

    gui = None
    if sys.platform == "win32":
        gui = "edgechromium"

    try:
        webview.start(debug=False, gui=gui)
    finally:
        stop_tick.set()
        backend.shutdown()
