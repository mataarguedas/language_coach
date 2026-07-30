"""Unit tests for services/prosody.py.

All tests use synthetically generated fixture WAVs (see conftest.py) so that
behaviour is deterministic.  No language branching is present in the service
and none is tested here — the same assertions hold for any language's audio.

Tests are organised into five sections:
  1. Edge cases (empty array, zero-length)
  2. Duration accuracy
  3. Speaking rate (voiced/silent discrimination)
  4. Pause detection (count and rough position)
  5. Energy envelope (shape, range, silent vs. tonal contrast)
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.services.prosody import ProsodyResult, extract

SR = 16000  # must match conftest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sine(freq: float, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    return (amplitude * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def _silence(duration_s: float) -> np.ndarray:
    return np.zeros(int(SR * duration_s), dtype=np.float32)


# ---------------------------------------------------------------------------
# 1. Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_ndarray_returns_zero_result(self):
        result = extract(np.array([], dtype=np.float32), sr=SR)
        assert result.duration_s == 0.0
        assert result.speaking_rate == 0.0
        assert result.pause_count == 0
        assert result.pause_positions_s == []
        assert result.energy_envelope == []

    def test_returns_prosody_result_dataclass(self, wav_dir):
        result = extract(wav_dir["short"])
        assert isinstance(result, ProsodyResult)

    def test_accepts_path_object(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert result.duration_s > 0

    def test_accepts_string_path(self, wav_dir):
        result = extract(str(wav_dir["tone"]))
        assert result.duration_s > 0

    def test_accepts_ndarray_directly(self):
        y = _sine(440, 1.0)
        result = extract(y, sr=SR)
        assert result.duration_s == pytest.approx(1.0, abs=0.05)

    def test_short_clip_does_not_raise(self, wav_dir):
        result = extract(wav_dir["short"])
        assert result.duration_s == pytest.approx(0.3, abs=0.05)


# ---------------------------------------------------------------------------
# 2. Duration accuracy
# ---------------------------------------------------------------------------

class TestDuration:
    def test_silence_duration(self, wav_dir):
        result = extract(wav_dir["silence"])
        assert result.duration_s == pytest.approx(2.0, abs=0.01)

    def test_tone_duration(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert result.duration_s == pytest.approx(2.0, abs=0.01)

    def test_one_pause_duration(self, wav_dir):
        # 0.5 + 0.5 + 0.5 = 1.5 s
        result = extract(wav_dir["one_pause"])
        assert result.duration_s == pytest.approx(1.5, abs=0.01)

    def test_two_pauses_duration(self, wav_dir):
        # 0.3 * 3 + 0.3 * 2 = 1.5 s
        result = extract(wav_dir["two_pauses"])
        assert result.duration_s == pytest.approx(1.5, abs=0.01)

    def test_ndarray_duration_matches_sample_count(self):
        duration = 0.75
        y = _sine(440, duration)
        result = extract(y, sr=SR)
        assert result.duration_s == pytest.approx(duration, abs=0.01)


# ---------------------------------------------------------------------------
# 3. Speaking rate
# ---------------------------------------------------------------------------

class TestSpeakingRate:
    def test_silence_has_zero_speaking_rate(self, wav_dir):
        result = extract(wav_dir["silence"])
        assert result.speaking_rate == 0.0

    def test_tone_has_positive_speaking_rate(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert result.speaking_rate > 0

    def test_speaking_rate_is_non_negative(self, wav_dir):
        for name in ("silence", "tone", "one_pause", "two_pauses"):
            assert extract(wav_dir[name]).speaking_rate >= 0.0

    def test_tone_rate_higher_than_half_silent(self):
        # Full tone should have higher rate than 50 % silent clip.
        full = extract(_sine(440, 2.0), sr=SR)
        half = extract(
            np.concatenate([_sine(440, 1.0), _silence(1.0)]), sr=SR
        )
        assert full.speaking_rate > half.speaking_rate

    def test_speaking_rate_units_are_frames_per_second(self, wav_dir):
        # For a 2 s clip, rate ≤ total_pitch_frames / duration — sanity only.
        result = extract(wav_dir["tone"])
        # Praat default time step ≈ 0.01 s → ~200 frames for 2 s clip.
        # Rate = voiced_frames / 2 ≈ 100.  Accept broad range.
        assert 1.0 < result.speaking_rate < 500.0


# ---------------------------------------------------------------------------
# 4. Pause detection
# ---------------------------------------------------------------------------

class TestPauseDetection:
    def test_no_pauses_in_continuous_tone(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert result.pause_count == 0
        assert result.pause_positions_s == []

    def test_no_pauses_in_silence(self, wav_dir):
        # Pure silence has no voiced intervals, so no gaps between them.
        result = extract(wav_dir["silence"])
        assert result.pause_count == 0

    def test_one_pause_detected(self, wav_dir):
        result = extract(wav_dir["one_pause"])
        assert result.pause_count == 1

    def test_two_pauses_detected(self, wav_dir):
        result = extract(wav_dir["two_pauses"])
        assert result.pause_count == 2

    def test_pause_position_within_tolerance(self, wav_dir):
        # Pause starts at 0.5 s; frame quantisation may shift it by ≤ ~0.15 s.
        result = extract(wav_dir["one_pause"])
        assert len(result.pause_positions_s) == 1
        assert result.pause_positions_s[0] == pytest.approx(0.5, abs=0.15)

    def test_pause_positions_are_sorted(self, wav_dir):
        result = extract(wav_dir["two_pauses"])
        positions = result.pause_positions_s
        assert positions == sorted(positions)

    def test_pause_positions_within_duration(self, wav_dir):
        result = extract(wav_dir["two_pauses"])
        for pos in result.pause_positions_s:
            assert 0.0 <= pos < result.duration_s

    def test_pause_count_matches_positions_length(self, wav_dir):
        for name in ("tone", "one_pause", "two_pauses"):
            result = extract(wav_dir[name])
            assert result.pause_count == len(result.pause_positions_s)

    def test_min_pause_s_filters_short_gaps(self):
        # 0.05 s gap — below default 0.1 s threshold → not counted.
        y = np.concatenate([_sine(440, 0.5), _silence(0.05), _sine(440, 0.5)])
        result = extract(y, sr=SR, min_pause_s=0.1)
        assert result.pause_count == 0

    def test_min_pause_s_includes_gap_above_threshold(self):
        y = np.concatenate([_sine(440, 0.5), _silence(0.3), _sine(440, 0.5)])
        result = extract(y, sr=SR, min_pause_s=0.1)
        assert result.pause_count == 1


# ---------------------------------------------------------------------------
# 5. Energy envelope
# ---------------------------------------------------------------------------

class TestEnergyEnvelope:
    def test_envelope_is_nonempty_for_nonzero_audio(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert len(result.energy_envelope) > 0

    def test_envelope_values_in_unit_range(self, wav_dir):
        result = extract(wav_dir["tone"])
        arr = np.array(result.energy_envelope)
        assert float(arr.min()) >= 0.0
        assert float(arr.max()) <= 1.0 + 1e-6

    def test_silent_envelope_all_zeros(self, wav_dir):
        result = extract(wav_dir["silence"])
        assert all(v == pytest.approx(0.0) for v in result.energy_envelope)

    def test_tone_envelope_max_is_one(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert max(result.energy_envelope) == pytest.approx(1.0, abs=1e-4)

    def test_envelope_length_matches_expected_frames(self, wav_dir):
        # n_frames = ceil(n_samples / hop_length) from librosa (center padding).
        result = extract(wav_dir["tone"])
        import math
        n_samples = int(SR * 2.0)
        hop = 512
        expected_frames = math.ceil(n_samples / hop)
        # Allow ±1 for rounding differences in librosa versions.
        assert abs(len(result.energy_envelope) - expected_frames) <= 1

    def test_pause_lowers_envelope_mid_clip(self, wav_dir):
        result = extract(wav_dir["one_pause"])
        arr = np.array(result.energy_envelope)
        # Middle third of the clip should be lower than the outer thirds.
        n = len(arr)
        third = n // 3
        middle_mean = float(arr[third : 2 * third].mean())
        outer_mean = float((arr[:third].mean() + arr[2 * third:].mean()) / 2)
        assert middle_mean < outer_mean

    def test_envelope_type_is_list_of_floats(self, wav_dir):
        result = extract(wav_dir["tone"])
        assert isinstance(result.energy_envelope, list)
        assert all(isinstance(v, float) for v in result.energy_envelope)


# ---------------------------------------------------------------------------
# 6. Language-agnostic: identical logic for different "language" signals
# ---------------------------------------------------------------------------

class TestLanguageAgnostic:
    """Demonstrate that the function is language-blind — two clips with
    structurally identical pause patterns but different pitches (simulating
    e.g. Mandarin vs English prosody range) produce the same pause count."""

    def test_same_pause_count_different_pitch(self):
        low_pitch = np.concatenate([_sine(150, 0.5), _silence(0.4), _sine(150, 0.5)])
        high_pitch = np.concatenate([_sine(800, 0.5), _silence(0.4), _sine(800, 0.5)])
        r_low = extract(low_pitch, sr=SR)
        r_high = extract(high_pitch, sr=SR)
        assert r_low.pause_count == r_high.pause_count == 1

    def test_duration_independent_of_pitch(self):
        for freq in (150, 440, 800):
            result = extract(_sine(freq, 1.5), sr=SR)
            assert result.duration_s == pytest.approx(1.5, abs=0.01)
