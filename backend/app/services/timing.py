"""Token timing allocator.

Pure function — takes an ordered token list and a total clip duration in
milliseconds, and returns a list of TimingEntry objects with per-token
start/end offsets.  No language branching, no network calls.

Algorithm
---------
Each token receives a weight equal to its character count.  Tokens consisting
entirely of pause-worthy punctuation (。！？…，；：,.!?;:—–) receive
PAUSE_MULTIPLIER × that count so karaoke highlighting lingers at sentence
boundaries.  Durations are then allocated proportionally and cumulated;
the final entry is snapped to exactly *total_ms* to absorb rounding drift.
"""

import re

from app.models.synthesize import TimingEntry
from app.models.token import Token

_PAUSE_RE = re.compile(r"^[。！？…、，；：,.!?;:\-—–]+$")
PAUSE_MULTIPLIER: float = 2.5


def _weight(token: Token) -> float:
    n = len(token.text)
    return n * (PAUSE_MULTIPLIER if _PAUSE_RE.match(token.text) else 1.0)


def allocate(tokens: list[Token], total_ms: int) -> list[TimingEntry]:
    """Distribute *total_ms* across *tokens*, returning ordered TimingEntry objects.

    Returns an empty list when *tokens* is empty or *total_ms* is non-positive.
    Entries are contiguous: each entry's start_ms equals the previous entry's end_ms.
    """
    if not tokens or total_ms <= 0:
        return []

    weights = [_weight(t) for t in tokens]
    total_weight = sum(weights)

    entries: list[TimingEntry] = []
    cursor_ms = 0
    last = len(tokens) - 1
    for i, (token, weight) in enumerate(zip(tokens, weights)):
        end_ms = total_ms if i == last else cursor_ms + round(weight / total_weight * total_ms)
        entries.append(TimingEntry(token=token, start_ms=cursor_ms, end_ms=end_ms))
        cursor_ms = end_ms

    return entries
