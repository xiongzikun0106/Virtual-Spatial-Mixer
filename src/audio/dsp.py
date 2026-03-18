import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi


class RealtimeLPF:
    """Stateful streaming Butterworth low-pass filter (per-channel)."""

    def __init__(self, sample_rate: int, initial_cutoff: float = 20000.0, order: int = 2):
        self.fs = sample_rate
        self.order = order
        self._current_cutoff = -1.0
        self.b = np.array([1.0])
        self.a = np.array([1.0])
        self.zi_l: np.ndarray | None = None
        self.zi_r: np.ndarray | None = None
        self._update_coefficients(initial_cutoff)

    def _update_coefficients(self, cutoff: float):
        cutoff = max(20.0, min(cutoff, self.fs * 0.49))
        if abs(cutoff - self._current_cutoff) < 1.0:
            return
        self._current_cutoff = cutoff
        self.b, self.a = butter(self.order, cutoff, fs=self.fs, btype='low')
        zi_template = lfilter_zi(self.b, self.a)
        if self.zi_l is None or len(self.zi_l) != len(zi_template):
            self.zi_l = zi_template * 0.0
            self.zi_r = zi_template * 0.0

    def process(self, block: np.ndarray, cutoff: float) -> np.ndarray:
        self._update_coefficients(cutoff)
        if block.shape[0] == 0:
            return block
        out_l, self.zi_l = lfilter(self.b, self.a, block[:, 0], zi=self.zi_l)
        out_r, self.zi_r = lfilter(self.b, self.a, block[:, 1], zi=self.zi_r)
        return np.column_stack([out_l, out_r]).astype(np.float32)

    def reset(self):
        self.zi_l = None
        self.zi_r = None
        self._current_cutoff = -1.0
        self._update_coefficients(20000.0)


class DSPChain:
    """Per-track DSP: gain -> LPF -> stereo panning."""

    def __init__(self, sample_rate: int):
        self.lpf = RealtimeLPF(sample_rate)

    def process(self, block: np.ndarray, gain: float, pan: float, cutoff: float) -> np.ndarray:
        if block.shape[0] == 0:
            return block

        block = block * gain

        block = self.lpf.process(block, cutoff)

        pan_norm = (pan + 1.0) * 0.5  # 0..1, 0=left, 1=right
        left_gain = np.cos(pan_norm * np.pi * 0.5)
        right_gain = np.sin(pan_norm * np.pi * 0.5)
        block[:, 0] *= left_gain
        block[:, 1] *= right_gain

        return block

    def reset(self):
        self.lpf.reset()
