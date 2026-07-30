"""Tests for POST /api/synthesize.

Fish Audio HTTP calls are always mocked — the network is never touched.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.services.cache as cache_mod

FISH_KEY = "test-fish-key"
VALID_VOICE_EN = "fish-en-001"
VALID_VOICE_ZH = "fish-zh-001"
VALID_VOICE_ES = "fish-es-001"
FAKE_MP3 = b"\xff\xfb\x90" + b"audio" * 100  # fake MP3 bytes


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def client():
    return TestClient(app)


def _post(client, body: dict, fish_key: str | None = FISH_KEY):
    headers = {}
    if fish_key is not None:
        headers["X-Fish-Key"] = fish_key
    return client.post("/api/synthesize", json=body, headers=headers)


def _valid_body(**overrides) -> dict:
    base = {
        "text": "Hello world",
        "language": "en",
        "voice_id": VALID_VOICE_EN,
        "speed": 1.0,
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Missing / empty Fish key → 422
# ---------------------------------------------------------------------------

def test_missing_fish_key_returns_422(client):
    resp = _post(client, _valid_body(), fish_key=None)
    assert resp.status_code == 422
    assert "X-Fish-Key" in resp.json()["detail"]


def test_empty_fish_key_returns_422(client):
    resp = _post(client, _valid_body(), fish_key="")
    assert resp.status_code == 422
    assert "X-Fish-Key" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Character limit
# ---------------------------------------------------------------------------

def test_text_over_limit_returns_422(client):
    resp = _post(client, _valid_body(text="x" * 501))
    assert resp.status_code == 422
    assert "500" in resp.json()["detail"]


def test_text_at_limit_is_accepted(client):
    with patch(
        "app.routers.synthesize.fish_synthesize",
        new=AsyncMock(return_value=FAKE_MP3),
    ):
        resp = _post(client, _valid_body(text="x" * 500))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Voice ↔ language mismatch
# ---------------------------------------------------------------------------

def test_voice_language_mismatch_returns_4xx(client):
    # zh voice requested with es language
    resp = _post(client, _valid_body(language="es", voice_id=VALID_VOICE_ZH))
    assert resp.status_code in (404, 422)


def test_unknown_voice_returns_404(client):
    resp = _post(client, _valid_body(voice_id="fish-xx-999"))
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Invalid speed preset
# ---------------------------------------------------------------------------

def test_invalid_speed_returns_422(client):
    resp = _post(client, _valid_body(speed=0.5))
    assert resp.status_code == 422
    assert "preset" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# Cache miss → Fish called; result persisted
# ---------------------------------------------------------------------------

def test_cache_miss_calls_fish_and_persists(client, isolated_cache):
    mock_fish = AsyncMock(return_value=FAKE_MP3)
    with patch("app.routers.synthesize.fish_synthesize", new=mock_fish):
        resp = _post(client, _valid_body())

    assert resp.status_code == 200
    mock_fish.assert_awaited_once()

    data = resp.json()
    cache_key = data["cache_key"]
    assert cache_mod.exists(cache_key), "Audio must be persisted to disk on cache miss"
    entry = cache_mod.get(cache_key)
    assert entry is not None
    assert entry.audio == FAKE_MP3


# ---------------------------------------------------------------------------
# Cache hit → Fish NOT called
# ---------------------------------------------------------------------------

def test_cache_hit_skips_fish(client, isolated_cache):
    body = _valid_body()
    key = cache_mod.make_key(body["text"], body["language"], body["voice_id"], body["speed"])
    meta = {"total_ms": 1200, "entries": [], "language": "en", "voice_id": VALID_VOICE_EN, "speed": 1.0}
    cache_mod.put(key, FAKE_MP3, meta)

    mock_fish = AsyncMock(return_value=b"should-not-be-used")
    with patch("app.routers.synthesize.fish_synthesize", new=mock_fish):
        resp = _post(client, body)

    assert resp.status_code == 200
    mock_fish.assert_not_awaited()


# ---------------------------------------------------------------------------
# Response shape
# ---------------------------------------------------------------------------

def test_response_shape(client):
    with patch(
        "app.routers.synthesize.fish_synthesize",
        new=AsyncMock(return_value=FAKE_MP3),
    ):
        resp = _post(client, _valid_body())

    assert resp.status_code == 200
    data = resp.json()
    assert data["language"] == "en"
    assert data["voice_id"] == VALID_VOICE_EN
    assert data["speed"] == 1.0
    assert data["cache_key"]
    assert data["audio_url"].startswith("/api/synthesize/audio/")
    assert "timing" in data
    assert "total_ms" in data["timing"]
    assert "entries" in data["timing"]


# ---------------------------------------------------------------------------
# Audio serving endpoint
# ---------------------------------------------------------------------------

def test_audio_endpoint_serves_cached_mp3(client, isolated_cache):
    body = _valid_body()
    key = cache_mod.make_key(body["text"], body["language"], body["voice_id"], body["speed"])
    cache_mod.put(key, FAKE_MP3, {"total_ms": 0, "entries": []})

    resp = client.get(f"/api/synthesize/audio/{key}")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "audio/mpeg"
    assert resp.content == FAKE_MP3


def test_audio_endpoint_404_on_unknown_key(client):
    resp = client.get("/api/synthesize/audio/deadbeef" * 8)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Speed presets accepted
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("speed", [0.7, 0.85, 1.0, 1.15])
def test_all_speed_presets_accepted(client, speed):
    with patch(
        "app.routers.synthesize.fish_synthesize",
        new=AsyncMock(return_value=FAKE_MP3),
    ):
        resp = _post(client, _valid_body(speed=speed))
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Language discrimination in cache key (Fish must not be called twice for same inputs)
# ---------------------------------------------------------------------------

def test_different_languages_produce_different_cache_keys(client, isolated_cache):
    """Identical text+voice prefix but different language must hit separate cache entries."""
    mock_fish = AsyncMock(return_value=FAKE_MP3)
    with patch("app.routers.synthesize.fish_synthesize", new=mock_fish):
        r1 = _post(client, _valid_body(language="en", voice_id=VALID_VOICE_EN))
        r2 = _post(client, _valid_body(language="es", voice_id=VALID_VOICE_ES))

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["cache_key"] != r2.json()["cache_key"]
