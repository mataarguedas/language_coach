"""Shared pytest fixtures — synthetic WAV files for prosody tests.

All audio is generated programmatically so no binary assets are committed.
Files are written once per test session to a tmp directory.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

SR = 16000  # sample rate used for all fixture WAVs


# ---------------------------------------------------------------------------
# Low-level builders
# ---------------------------------------------------------------------------

def _sine(freq: float, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    return (amplitude * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def _silence(duration_s: float) -> np.ndarray:
    return np.zeros(int(SR * duration_s), dtype=np.float32)


def _write(path: Path, audio: np.ndarray) -> Path:
    sf.write(str(path), audio, SR)
    return path


# ---------------------------------------------------------------------------
# Session-scoped fixture directory
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def wav_dir(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    """Return a dict mapping fixture name → Path to a generated WAV file."""
    d = tmp_path_factory.mktemp("prosody_wavs")

    wavs: dict[str, Path] = {}

    # 2 s of pure silence
    wavs["silence"] = _write(d / "silence.wav", _silence(2.0))

    # 2 s of a continuous 440 Hz sine (speech-like, no pauses)
    wavs["tone"] = _write(d / "tone.wav", _sine(440, 2.0))

    # 0.5 s tone | 0.5 s silence | 0.5 s tone  →  1 pause
    wavs["one_pause"] = _write(
        d / "one_pause.wav",
        np.concatenate([_sine(440, 0.5), _silence(0.5), _sine(440, 0.5)]),
    )

    # tone | silence | tone | silence | tone  →  2 pauses
    wavs["two_pauses"] = _write(
        d / "two_pauses.wav",
        np.concatenate([
            _sine(440, 0.3), _silence(0.3),
            _sine(440, 0.3), _silence(0.3),
            _sine(440, 0.3),
        ]),
    )

    # Short clip — 0.3 s tone (tests small-file handling)
    wavs["short"] = _write(d / "short.wav", _sine(440, 0.3))

    return wavs
