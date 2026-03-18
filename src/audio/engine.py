import threading
import numpy as np
import sounddevice as sd

from src.constants import SAMPLE_RATE, BLOCK_SIZE, CHANNELS


class AudioEngine:
    """Callback-driven audio output via sounddevice.

    The playback_frame counter acts as the authoritative clock that the
    UI layer polls for synchronisation.
    """

    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.block_size = BLOCK_SIZE
        self.playback_frame = 0
        self.playing = False
        self.tracks = []  # List[TrackBuffer]
        self._lock = threading.Lock()

        self._param_callback = None  # (track, frame) -> (gain, pan, cutoff)

        self.stream = sd.OutputStream(
            samplerate=self.sample_rate,
            blocksize=self.block_size,
            channels=CHANNELS,
            dtype="float32",
            callback=self._callback,
        )

    def set_param_callback(self, fn):
        self._param_callback = fn

    def _callback(self, outdata: np.ndarray, frames: int, time_info, status):
        if not self.playing:
            outdata[:] = 0
            return

        mixed = np.zeros((frames, 2), dtype=np.float32)
        current_frame = self.playback_frame

        any_solo = any(t.solo for t in self.tracks)

        for track in self.tracks:
            if track.muted:
                continue
            if any_solo and not track.solo:
                continue

            chunk = track.read(current_frame, frames)

            if self._param_callback is not None:
                gain, pan, cutoff = self._param_callback(track, current_frame)
            else:
                gain, pan, cutoff = 1.0, 0.0, 20000.0

            gain *= track.duck_gain
            processed = track.dsp.process(chunk, gain, pan, cutoff)
            mixed += processed

        peak = np.max(np.abs(mixed))
        if peak > 1.0:
            mixed /= peak

        outdata[:] = mixed
        self.playback_frame += frames

    def add_track(self, track):
        with self._lock:
            self.tracks.append(track)

    def remove_track(self, track):
        with self._lock:
            if track in self.tracks:
                self.tracks.remove(track)

    def play(self):
        if not self.stream.active:
            self.stream.start()
        self.playing = True

    def pause(self):
        self.playing = False

    def stop(self):
        self.playing = False
        self.playback_frame = 0
        for t in self.tracks:
            t.dsp.reset()

    def seek(self, frame: int):
        self.playback_frame = max(0, frame)
        for t in self.tracks:
            t.dsp.reset()

    def get_time(self) -> float:
        return self.playback_frame / self.sample_rate

    def get_max_duration(self) -> float:
        if not self.tracks:
            return 0.0
        return max(t.duration for t in self.tracks)

    def shutdown(self):
        self.playing = False
        if self.stream.active:
            self.stream.stop()
        self.stream.close()
