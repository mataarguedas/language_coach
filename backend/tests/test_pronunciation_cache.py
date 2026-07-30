"""Unit tests for the pronunciation-result cache.

Covers the invariants that matter for cost + privacy:
  * key stability across calls
  * key changes when either input (target_cache_key or learner_audio_hash) changes
  * round-trip write/read via pydantic
  * cache directory never contains anything other than <key>.json
    (learner audio must never touch disk — see CLAUDE.md "Caching")
"""

from __future__ import annotations

import pytest

import app.services.pronunciation_cache as pc
from app.models.shadow import PronunciationResult, PronunciationWord


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def sample_result() -> PronunciationResult:
    return PronunciationResult(
        overall_score=87.5,
        words=[
            PronunciationWord(text="hello", accuracy_score=95.0, status="correct"),
            PronunciationWord(text="world", accuracy_score=60.0, status="mispronounced"),
        ],
    )


# Two arbitrary but valid sha256 hex digests to use as (target key, audio hash).
TARGET_KEY_A = "a" * 64
TARGET_KEY_B = "b" * 64
LEARNER_HASH_1 = "1" * 64
LEARNER_HASH_2 = "2" * 64


# ---------------------------------------------------------------------------
# Key stability + differentiation
# ---------------------------------------------------------------------------

def test_same_inputs_produce_same_key():
    assert pc.make_key(TARGET_KEY_A, LEARNER_HASH_1) == pc.make_key(
        TARGET_KEY_A, LEARNER_HASH_1
    )


def test_key_is_64_hex_chars():
    k = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)


def test_different_target_key_produces_different_key():
    assert pc.make_key(TARGET_KEY_A, LEARNER_HASH_1) != pc.make_key(
        TARGET_KEY_B, LEARNER_HASH_1
    )


def test_different_learner_hash_produces_different_key():
    assert pc.make_key(TARGET_KEY_A, LEARNER_HASH_1) != pc.make_key(
        TARGET_KEY_A, LEARNER_HASH_2
    )


def test_hash_audio_is_deterministic():
    assert pc.hash_audio(b"webm-opus-bytes") == pc.hash_audio(b"webm-opus-bytes")


def test_hash_audio_differs_by_content():
    assert pc.hash_audio(b"take-one") != pc.hash_audio(b"take-two")


# ---------------------------------------------------------------------------
# Round-trip write/read
# ---------------------------------------------------------------------------

def test_get_returns_none_on_miss():
    key = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    assert pc.get(key) is None
    assert not pc.exists(key)


def test_put_then_exists(sample_result):
    key = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    pc.put(key, sample_result)
    assert pc.exists(key)


def test_put_then_get_roundtrip(sample_result):
    key = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    pc.put(key, sample_result)

    got = pc.get(key)
    assert got is not None
    assert got == sample_result


def test_hit_avoids_regeneration(sample_result):
    """The whole point of this cache: a hit means Azure is not called."""
    key = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    pc.put(key, sample_result)

    azure_called = False

    def fake_azure_call() -> PronunciationResult:
        nonlocal azure_called
        azure_called = True
        raise AssertionError("Azure must not be called on a cache hit")

    result = pc.get(key) if pc.exists(key) else fake_azure_call()
    assert not azure_called
    assert result == sample_result


# ---------------------------------------------------------------------------
# Disk invariants — no audio must ever appear in the cache directory
# ---------------------------------------------------------------------------

def _pronunciation_dir(root):
    return root / "pronunciation"


def test_cache_directory_contains_only_json(sample_result, isolated_cache):
    """After several puts, every file in the pronunciation cache directory
    must be a .json — no .mp3/.wav/.webm/.opus/.raw or extensionless blobs.
    Guards CLAUDE.md's "learner audio never written to disk"."""
    for i in range(4):
        result = PronunciationResult(
            overall_score=float(50 + i),
            words=[PronunciationWord(text=f"w{i}", accuracy_score=90.0, status="correct")],
        )
        key = pc.make_key(TARGET_KEY_A, f"{i:0>64}")
        pc.put(key, result)

    files = list(_pronunciation_dir(isolated_cache).iterdir())
    assert len(files) == 4
    for f in files:
        assert f.suffix == ".json", f"Unexpected non-JSON file in cache: {f.name}"

    # And explicitly: no audio-looking artifacts.
    audio_exts = {".mp3", ".wav", ".webm", ".opus", ".ogg", ".m4a", ".raw", ".pcm"}
    for f in files:
        assert f.suffix not in audio_exts


def test_put_signature_does_not_accept_audio_bytes(sample_result):
    """Structural guarantee: put() takes a PronunciationResult, not bytes.
    A caller cannot accidentally hand it learner audio."""
    key = pc.make_key(TARGET_KEY_A, LEARNER_HASH_1)
    with pytest.raises((TypeError, AttributeError)):
        pc.put(key, b"raw-audio-bytes")  # type: ignore[arg-type]
