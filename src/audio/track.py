import numpy as np
import soundfile as sf

from src.audio.dsp import DSPChain
from src.constants import SAMPLE_RATE


class TrackBuffer:
    """Holds PCM data for a single audio track and provides block reads."""

    def __init__(self, filepath: str, track_id: int, name: str = ""):
        self.track_id = track_id
        self.name = name or filepath.split("/")[-1].split("\\")[-1]
        self.filepath = filepath

        data, sr = sf.read(filepath, dtype="float32", always_2d=True)
        if sr != SAMPLE_RATE:
            data = self._resample(data, sr, SAMPLE_RATE)
        if data.shape[1] == 1:
            data = np.column_stack([data, data])
        elif data.shape[1] > 2:
            data = data[:, :2]
        self.data = data
        self.num_frames = data.shape[0]
        self.duration = self.num_frames / SAMPLE_RATE

        self.dsp = DSPChain(SAMPLE_RATE)

        self.muted = False
        self.solo = False
        self.priority = 0
        self.duck_gain = 1.0

    @staticmethod
    def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        from scipy.signal import resample
        ratio = target_sr / orig_sr
        new_length = int(data.shape[0] * ratio)
        return resample(data, new_length).astype(np.float32)

    def read(self, start_frame: int, num_frames: int) -> np.ndarray:
        if start_frame >= self.num_frames or start_frame < 0:
            return np.zeros((num_frames, 2), dtype=np.float32)

        end = min(start_frame + num_frames, self.num_frames)
        chunk = self.data[start_frame:end]

        if chunk.shape[0] < num_frames:
            pad = np.zeros((num_frames - chunk.shape[0], 2), dtype=np.float32)
            chunk = np.concatenate([chunk, pad], axis=0)

        return chunk.copy()

    def get_waveform_overview(self, num_bins: int = 800) -> np.ndarray:
        """Return downsampled absolute-amplitude envelope for timeline display."""
        mono = np.mean(np.abs(self.data), axis=1)
        bin_size = max(1, len(mono) // num_bins)
        trimmed = mono[:bin_size * num_bins]
        return trimmed.reshape(num_bins, bin_size).max(axis=1)
