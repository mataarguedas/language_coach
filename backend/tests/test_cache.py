import os
from unittest.mock import patch

import pytest

import app.services.cache as cache_mod
from app.services.cache import CacheEntry, exists, get, make_key, put


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Route every cache operation to a throwaway temp directory."""
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    yield tmp_path


# ---------------------------------------------------------------------------
# (a) Key stability
# ---------------------------------------------------------------------------

def test_same_inputs_produce_same_key():
    k1 = make_key("hello", "en", "fish-en-001", 1.0)
    k2 = make_key("hello", "en", "fish-en-001", 1.0)
    assert k1 == k2


def test_key_is_64_hex_chars():
    k = make_key("hello", "en", "fish-en-001", 1.0)
    assert len(k) == 64
    assert all(c in "0123456789abcdef" for c in k)


def test_different_text_different_key():
    assert make_key("hello", "en", "fish-en-001", 1.0) != make_key(
        "world", "en", "fish-en-001", 1.0
    )


def test_different_voice_different_key():
    assert make_key("hello", "en", "fish-en-001", 1.0) != make_key(
        "hello", "en", "fish-en-002", 1.0
    )


def test_different_speed_different_key():
    assert make_key("hello", "en", "fish-en-001", 1.0) != make_key(
        "hello", "en", "fish-en-001", 0.7
    )


# ---------------------------------------------------------------------------
# (b) Same text+voice+speed but different language → different keys
# ---------------------------------------------------------------------------

def test_language_discrimination_zh_vs_es():
    k_zh = make_key("hello", "zh", "fish-zh-001", 1.0)
    k_es = make_key("hello", "es", "fish-zh-001", 1.0)
    assert k_zh != k_es, "Different languages must produce different cache keys"


def test_language_discrimination_es_vs_en():
    k_es = make_key("hello", "es", "fish-es-001", 1.0)
    k_en = make_key("hello", "en", "fish-es-001", 1.0)
    assert k_es != k_en, "Different languages must produce different cache keys"


def test_language_discrimination_all_three():
    keys = {
        make_key("你好", lang, "v1", 1.0) for lang in ("zh", "es", "en")
    }
    assert len(keys) == 3, "All three language variants must produce distinct keys"


# ---------------------------------------------------------------------------
# (c) Cache hit avoids regeneration
# ---------------------------------------------------------------------------

def test_exists_false_before_put():
    key = make_key("hola", "es", "fish-es-001", 1.0)
    assert not exists(key)


def test_put_then_exists():
    key = make_key("hola", "es", "fish-es-001", 1.0)
    put(key, b"audio-bytes", {"total_ms": 1000})
    assert exists(key)


def test_get_returns_none_on_miss():
    key = make_key("hola", "es", "fish-es-001", 1.0)
    assert get(key) is None


def test_put_then_get_roundtrip():
    key = make_key("hola", "es", "fish-es-001", 1.0)
    audio = b"\xff\xfb\x90audio-data"
    meta = {"total_ms": 2500, "language": "es", "voice_id": "fish-es-001"}

    put(key, audio, meta)
    entry = get(key)

    assert isinstance(entry, CacheEntry)
    assert entry.audio == audio
    assert entry.meta == meta


def test_hit_does_not_need_regeneration():
    """Simulate the synthesize flow: if exists() is True, get() must succeed
    and we must NOT need to call the Fish API (represented here by a sentinel)."""
    key = make_key("buenos días", "es", "fish-es-002", 0.85)
    audio = b"fish-mp3-data"
    meta = {"total_ms": 1800, "language": "es"}

    # Prime the cache
    put(key, audio, meta)

    fish_called = False

    def fake_fish_call():
        nonlocal fish_called
        fish_called = True
        return b"should-not-be-returned"

    # The correct flow: check cache first, call Fish only on miss
    if exists(key):
        result = get(key)
    else:
        result = CacheEntry(audio=fake_fish_call(), meta={})

    assert not fish_called, "Fish API must not be called on a cache hit"
    assert result is not None
    assert result.audio == audio


def test_missing_mp3_returns_none(tmp_path):
    """Both sidecar files must be present; a partial write is treated as a miss."""
    key = make_key("partial", "en", "fish-en-001", 1.0)
    put(key, b"audio", {"total_ms": 500})

    # Remove the .mp3, leave the .json
    (tmp_path / f"{key}.mp3").unlink()
    assert get(key) is None
    assert not exists(key)


def test_missing_json_returns_none(tmp_path):
    """Both sidecar files must be present; a partial write is treated as a miss."""
    key = make_key("partial", "en", "fish-en-001", 1.0)
    put(key, b"audio", {"total_ms": 500})

    # Remove the .json, leave the .mp3
    (tmp_path / f"{key}.json").unlink()
    assert get(key) is None
    assert not exists(key)
