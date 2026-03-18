import numpy as np
import soundfile as sf

from src.constants import SAMPLE_RATE, BLOCK_SIZE
from src.audio.dsp import DSPChain


def export_mix(
    tracks,
    trajectories: dict,
    spatial_mapper,
    collision_resolver,
    output_path: str,
    progress_callback=None,
):
    """Offline render all tracks to a stereo WAV file.

    tracks: list of TrackBuffer objects
    trajectories: {track_id: Trajectory}
    spatial_mapper: SpatialMapper instance
    collision_resolver: CollisionResolver instance
    """
    if not tracks:
        return

    max_frames = max(t.num_frames for t in tracks)
    output = np.zeros((max_frames, 2), dtype=np.float32)

    dsps = {t.track_id: DSPChain(SAMPLE_RATE) for t in tracks}

    any_solo = any(t.solo for t in tracks)

    total_blocks = (max_frames + BLOCK_SIZE - 1) // BLOCK_SIZE

    for block_idx in range(total_blocks):
        start = block_idx * BLOCK_SIZE
        end = min(start + BLOCK_SIZE, max_frames)
        frames = end - start
        time_sec = start / SAMPLE_RATE

        positions = {}
        for t in tracks:
            traj = trajectories.get(t.track_id)
            if traj and traj.keyframes:
                positions[t.track_id] = traj.get_position(time_sec)
            else:
                positions[t.track_id] = np.zeros(3)

        twp = [
            (t.track_id, t.priority, positions[t.track_id])
            for t in tracks
        ]
        duck_gains = collision_resolver.resolve(twp)

        mixed = np.zeros((frames, 2), dtype=np.float32)

        for t in tracks:
            if t.muted:
                continue
            if any_solo and not t.solo:
                continue

            chunk = t.read(start, frames)
            pos = positions[t.track_id]
            gain, pan, cutoff = spatial_mapper.compute(pos)
            gain *= duck_gains.get(t.track_id, 1.0)

            processed = dsps[t.track_id].process(chunk, gain, pan, cutoff)
            mixed += processed

        peak = np.max(np.abs(mixed))
        if peak > 1.0:
            mixed /= peak

        output[start:end] = mixed

        if progress_callback and block_idx % 50 == 0:
            progress_callback(block_idx / total_blocks)

    sf.write(output_path, output, SAMPLE_RATE, subtype="FLOAT")

    if progress_callback:
        progress_callback(1.0)
