"""Unit tests for services/shadow_compare.py.

Feeds hand-built ProsodyResult values (no audio decoding) so behaviour is
deterministic. No language branching exists in the module and none is
tested here.
"""

from __future__ import annotations

import pytest

from app.services.prosody import ProsodyResult
from app.services.shadow_compare import compare, to_features


def _pr(
    duration_s: float,
    speaking_rate: float,
    pause_count: int = 0,
    pause_positions_s: list[float] | None = None,
    energy_envelope: list[float] | None = None,
) -> ProsodyResult:
    return ProsodyResult(
        duration_s=duration_s,
        speaking_rate=speaking_rate,
        pause_count=pause_count,
        pause_positions_s=pause_positions_s or [],
        energy_envelope=energy_envelope or [],
    )


# ---------------------------------------------------------------------------
# Score bounds
# ---------------------------------------------------------------------------

class TestScoreBounds:
    def test_identical_prosody_scores_100(self):
        pf = _pr(duration_s=2.0, speaking_rate=100.0)
        score, _ = compare(pf, pf)
        assert score == pytest.approx(100.0)

    def test_score_never_exceeds_100(self):
        target = _pr(2.0, 100.0)
        learner = _pr(2.0, 100.0)
        score, _ = compare(target, learner)
        assert 0 <= score <= 100

    def test_score_floored_at_zero(self):
        # Extreme deviation: learner is 10x slower on both axes.
        target = _pr(1.0, 100.0)
        learner = _pr(10.0, 10.0)
        score, _ = compare(target, learner)
        assert 0 <= score <= 100
        assert score < 10  # deep in the floor region

    def test_score_decreases_with_deviation(self):
        target = _pr(2.0, 100.0)
        close = _pr(2.1, 100.0)
        far = _pr(3.0, 100.0)
        s_close, _ = compare(target, close)
        s_far, _ = compare(target, far)
        assert s_close > s_far


# ---------------------------------------------------------------------------
# Tips content
# ---------------------------------------------------------------------------

class TestTips:
    def test_faster_learner_gets_faster_tip(self):
        target = _pr(2.0, 100.0)
        learner = _pr(1.4, 140.0)  # 30% shorter → 30% faster
        _, tips = compare(target, learner)
        joined = " ".join(tips).lower()
        assert "faster" in joined
        assert "30%" in joined  # matches the PRD example wording

    def test_slower_learner_gets_slower_tip(self):
        target = _pr(2.0, 100.0)
        learner = _pr(2.6, 70.0)  # 30% longer → 30% slower
        _, tips = compare(target, learner)
        joined = " ".join(tips).lower()
        assert "slower" in joined

    def test_matching_pace_gets_positive_tip(self):
        target = _pr(2.0, 100.0)
        learner = _pr(2.02, 100.0)  # <1% off
        _, tips = compare(target, learner)
        assert any("great" in t.lower() or "close" in t.lower() for t in tips)

    def test_extra_pauses_flagged(self):
        target = _pr(2.0, 100.0, pause_count=0)
        learner = _pr(2.0, 100.0, pause_count=5)
        _, tips = compare(target, learner)
        assert any("paused" in t.lower() for t in tips)

    def test_missing_pauses_flagged(self):
        target = _pr(2.0, 100.0, pause_count=5)
        learner = _pr(2.0, 100.0, pause_count=0)
        _, tips = compare(target, learner)
        assert any("pause" in t.lower() for t in tips)

    def test_half_clip_drift_flagged(self):
        # Target has energy centred; learner has all energy in the second half.
        target = _pr(2.0, 100.0, energy_envelope=[1.0] * 100)
        learner = _pr(2.0, 100.0, energy_envelope=[0.0] * 50 + [1.0] * 50)
        _, tips = compare(target, learner)
        joined = " ".join(tips).lower()
        assert "half" in joined

    def test_tips_never_empty(self):
        # Degenerate: no signal at all still returns something.
        target = _pr(0.0, 0.0)
        learner = _pr(0.0, 0.0)
        _, tips = compare(target, learner)
        assert len(tips) >= 1


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_zero_target_duration_does_not_crash(self):
        target = _pr(0.0, 0.0)
        learner = _pr(1.0, 50.0)
        score, tips = compare(target, learner)
        assert 0 <= score <= 100
        assert isinstance(tips, list)

    def test_zero_target_speaking_rate_falls_back_to_duration(self):
        target = _pr(2.0, 0.0)
        learner = _pr(2.0, 50.0)
        score, _ = compare(target, learner)
        # Duration matches perfectly → score = 100 * duration_component only.
        assert score == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# to_features projection
# ---------------------------------------------------------------------------

class TestToFeatures:
    def test_projects_all_wire_fields(self):
        pr = _pr(2.0, 50.0, pause_count=1, pause_positions_s=[0.5])
        pf = to_features(pr)
        assert pf.duration_s == 2.0
        assert pf.speaking_rate == 50.0
        assert pf.pause_count == 1
        assert pf.pause_positions_s == [0.5]

    def test_does_not_leak_energy_envelope(self):
        pr = _pr(2.0, 50.0, energy_envelope=[0.1, 0.2])
        pf = to_features(pr)
        assert not hasattr(pf, "energy_envelope")
