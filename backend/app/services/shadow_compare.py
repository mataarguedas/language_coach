"""Compare target vs learner prosody and produce shadowing feedback.

Language-independent: operates only on acoustic ``ProsodyResult`` values.

Entry point: ``compare(target, learner) -> (score, tips)``

- ``score``  : normalised pace-match, 0-100 (higher = closer to the target).
- ``tips``   : ordered human-readable guidance strings.

The score is a weighted blend of duration match (primary signal — same words
should take roughly the same time) and voiced-frame rate match (secondary
signal — captures speaking density when durations are close). A perfect match
scores 100; a 100 % deviation on either axis floors that component at 0.
"""

from __future__ import annotations

import numpy as np

from app.models.shadow import ProsodyFeatures
from app.services.prosody import ProsodyResult

# --- Tunables --------------------------------------------------------------
# Deviation (fraction) at or above which the corresponding score component
# reaches 0. 1.0 means "off by 100 %".
_DURATION_FLOOR = 1.0
_RATE_FLOOR = 1.0
# Weighting of the two score components. Duration is the more intuitive signal.
_W_DURATION = 0.7
_W_RATE = 0.3
# Only surface a pace tip when the deviation is meaningful.
_PACE_TIP_THRESHOLD_PCT = 10.0
# Half-clip check: only complain when the energy-midpoint drift exceeds this.
_HALF_DRIFT_THRESHOLD = 0.08
# Pause-count tip fires only when the differential exceeds this.
_PAUSE_DIFF_THRESHOLD = 1


def _energy_midpoint_fraction(env: list[float]) -> float | None:
    """Return the fraction of the clip at which cumulative energy = half total.

    Returns ``None`` when the envelope is empty or fully silent.
    """
    if not env:
        return None
    arr = np.asarray(env, dtype=np.float64)
    total = float(arr.sum())
    if total <= 0.0:
        return None
    cum = np.cumsum(arr)
    idx = int(np.searchsorted(cum, total / 2.0))
    idx = min(idx, len(arr) - 1)
    return (idx + 1) / len(arr)


def _pace_tip(delta_pct: float) -> str | None:
    if abs(delta_pct) < _PACE_TIP_THRESHOLD_PCT:
        return "Great pace — very close to the target."
    if delta_pct > 0:
        return f"You were {delta_pct:.0f}% slower than the target — try picking up the pace."
    return f"You were {abs(delta_pct):.0f}% faster than the target — try slowing down."


def _half_clip_tip(target: ProsodyResult, learner: ProsodyResult) -> str | None:
    t_mid = _energy_midpoint_fraction(target.energy_envelope)
    l_mid = _energy_midpoint_fraction(learner.energy_envelope)
    if t_mid is None or l_mid is None:
        return None
    drift = l_mid - t_mid
    if abs(drift) < _HALF_DRIFT_THRESHOLD:
        return None
    if drift > 0:
        # Learner reached the halfway point of speech later → first half dragged.
        return "Your first half ran long — try speeding up the opening."
    return "Your second half ran long — try slowing the opening or speeding up the ending."


def _pause_tip(target: ProsodyResult, learner: ProsodyResult) -> str | None:
    diff = learner.pause_count - target.pause_count
    if abs(diff) <= _PAUSE_DIFF_THRESHOLD:
        return None
    if diff > 0:
        return (
            f"You paused {diff} more time(s) than the target — try to speak more continuously."
        )
    return (
        f"The target paused {-diff} more time(s) — try adding brief pauses at punctuation."
    )


def _pace_match_score(
    duration_ratio: float | None,
    rate_ratio: float | None,
) -> float:
    """Blend duration and rate deviations into a 0-100 score."""
    if duration_ratio is not None:
        d_dev = min(abs(duration_ratio - 1.0) / _DURATION_FLOOR, 1.0)
        d_score = 1.0 - d_dev
    else:
        d_score = None

    if rate_ratio is not None:
        r_dev = min(abs(rate_ratio - 1.0) / _RATE_FLOOR, 1.0)
        r_score = 1.0 - r_dev
    else:
        r_score = None

    if d_score is None and r_score is None:
        return 0.0
    if r_score is None:
        return 100.0 * d_score
    if d_score is None:
        return 100.0 * r_score
    return 100.0 * (_W_DURATION * d_score + _W_RATE * r_score)


def compare(
    target: ProsodyResult,
    learner: ProsodyResult,
) -> tuple[float, list[str]]:
    """Return ``(pace_match_score, tips)`` for the learner against the target."""
    duration_ratio = (
        learner.duration_s / target.duration_s if target.duration_s > 0 else None
    )
    rate_ratio = (
        learner.speaking_rate / target.speaking_rate
        if target.speaking_rate > 0
        else None
    )

    score = _pace_match_score(duration_ratio, rate_ratio)

    tips: list[str] = []
    if duration_ratio is not None:
        delta_pct = (duration_ratio - 1.0) * 100.0
        tip = _pace_tip(delta_pct)
        if tip:
            tips.append(tip)

    half_tip = _half_clip_tip(target, learner)
    if half_tip:
        tips.append(half_tip)

    pause_tip = _pause_tip(target, learner)
    if pause_tip:
        tips.append(pause_tip)

    if not tips:
        tips.append("Not enough signal to compare — try a longer clip.")

    return score, tips


def to_features(result: ProsodyResult) -> ProsodyFeatures:
    """Project a full ProsodyResult onto the wire-level ProsodyFeatures model."""
    return ProsodyFeatures(
        duration_s=result.duration_s,
        speaking_rate=result.speaking_rate,
        pause_count=result.pause_count,
        pause_positions_s=result.pause_positions_s,
    )
