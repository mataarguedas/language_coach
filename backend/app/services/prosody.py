"""Prosodic feature extraction — pure functions, language-independent.

Entry point: ``extract(source, sr)``

``source`` may be a file path (``str`` or ``pathlib.Path``) or a mono
``numpy.ndarray`` of float32/float64 samples.  Returns a ``ProsodyResult``
dataclass with:

- ``duration_s``        — total clip length in seconds
- ``speaking_rate``     — voiced frames per second (Praat pitch tracking)
- ``pause_count``       — number of silence segments ≥ ``min_pause_s``
- ``pause_positions_s`` — start time (s) of each detected pause
- ``energy_envelope``   — per-hop-frame RMS energy, normalised to [0, 1]

No language branching anywhere in this module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import librosa
import numpy as np
import parselmouth


@dataclass
class ProsodyResult:
    duration_s: float
    speaking_rate: float
    pause_count: int
    pause_positions_s: list[float] = field(default_factory=list)
    energy_envelope: list[float] = field(default_factory=list)


def extract(
    source: str | Path | np.ndarray,
    sr: int = 16000,
    *,
    top_db: float = 30.0,
    frame_length: int = 2048,
    hop_length: int = 512,
    min_pause_s: float = 0.1,
) -> ProsodyResult:
    """Extract prosodic features from *source*.

    Parameters
    ----------
    source:
        File path **or** mono float ndarray of audio samples.
    sr:
        Target sample rate.  When *source* is a path, librosa resamples to
        this rate.  When *source* is an ndarray, this value is taken as-is.
    top_db:
        Threshold (dB below peak) used to split voiced/silent regions.
    frame_length, hop_length:
        STFT-style window and hop for RMS computation and split detection.
    min_pause_s:
        Minimum gap duration (seconds) that counts as a pause.
    """
    if isinstance(source, (str, Path)):
        y, sr = librosa.load(str(source), sr=sr, mono=True)
    else:
        y = np.asarray(source, dtype=np.float32)

    if len(y) == 0:
        return ProsodyResult(
            duration_s=0.0,
            speaking_rate=0.0,
            pause_count=0,
        )

    duration_s = float(len(y) / sr)

    # --- Speaking rate: voiced frames per second via Praat pitch analysis ----
    # parselmouth.Sound expects float64; ndarray may be float32.
    snd = parselmouth.Sound(y.astype(np.float64), sampling_frequency=sr)
    pitch = snd.to_pitch()
    # selected_array['frequency'] is 0.0 for unvoiced frames, >0 for voiced.
    freqs = pitch.selected_array["frequency"]
    n_voiced = int(np.sum(freqs > 0))
    speaking_rate = n_voiced / duration_s if duration_s > 0 else 0.0

    # --- Pause detection: gaps between non-silent intervals -------------------
    intervals = librosa.effects.split(
        y, top_db=top_db, frame_length=frame_length, hop_length=hop_length
    )

    pause_positions: list[float] = []
    for i in range(1, len(intervals)):
        gap_start = int(intervals[i - 1][1])
        gap_end = int(intervals[i][0])
        gap_s = (gap_end - gap_start) / sr
        if gap_s >= min_pause_s:
            pause_positions.append(float(gap_start / sr))

    # --- Energy envelope: per-frame RMS, normalised to [0, 1] ----------------
    rms = librosa.feature.rms(
        y=y, frame_length=frame_length, hop_length=hop_length
    )[0]
    peak = float(rms.max())
    energy_envelope: list[float] = (rms / peak).tolist() if peak > 0 else rms.tolist()

    return ProsodyResult(
        duration_s=duration_s,
        speaking_rate=float(speaking_rate),
        pause_count=len(pause_positions),
        pause_positions_s=pause_positions,
        energy_envelope=energy_envelope,
    )
