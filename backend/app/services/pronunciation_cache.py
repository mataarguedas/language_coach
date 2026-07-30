"""Content-addressable cache for pronunciation-assessment results.

Kept separate from :mod:`app.services.cache` (the TTS audio cache) because
this cache stores JSON only. Structural guarantee: :func:`put` accepts a
:class:`PronunciationResult` — not bytes — so learner audio cannot reach
disk through this module. Hash the audio in memory via :func:`hash_audio`,
then discard the bytes.

Cache key = ``sha256(target_cache_key + learner_audio_hash)``. Both inputs
are already hex-digest strings; a NUL separator eliminates any suffix-shift
concatenation collision. Same key on repeat analyses of the same
(target, learner) pair means Azure is never re-billed.

Files live under ``CACHE_DIR/pronunciation/<key>.json`` so the audio cache
directory and the pronunciation cache directory never share files — the
"no audio files in this directory" invariant is directly enumerable.

See CLAUDE.md "Caching" and "Security / cost guardrails".
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from app.models.shadow import PronunciationResult

_DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / ".cache"
_SUBDIR = "pronunciation"


def _cache_dir() -> Path:
    root = Path(os.environ.get("CACHE_DIR") or _DEFAULT_CACHE_DIR)
    path = root / _SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def hash_audio(audio_bytes: bytes) -> str:
    """SHA-256 hex digest of learner audio bytes.

    Compute this on the in-memory upload and discard the bytes. Never write
    learner audio to disk.
    """
    return hashlib.sha256(audio_bytes).hexdigest()


def make_key(target_cache_key: str, learner_audio_hash: str) -> str:
    """Stable cache key: sha256(target_cache_key + learner_audio_hash)."""
    canonical = "\x00".join([target_cache_key, learner_audio_hash])
    return hashlib.sha256(canonical.encode()).hexdigest()


def exists(key: str) -> bool:
    return (_cache_dir() / f"{key}.json").exists()


def get(key: str) -> PronunciationResult | None:
    path = _cache_dir() / f"{key}.json"
    if not path.exists():
        return None
    return PronunciationResult.model_validate_json(path.read_text())


def put(key: str, result: PronunciationResult) -> None:
    """Persist a pronunciation result. Only JSON — never audio."""
    path = _cache_dir() / f"{key}.json"
    path.write_text(result.model_dump_json())
