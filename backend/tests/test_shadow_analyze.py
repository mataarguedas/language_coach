"""Integration tests for POST /api/shadow/analyze.

Audio is generated in-memory as WAV so we don't rely on any binary fixtures
or the ffmpeg pipeline for decoding. The endpoint's decode/extract path
still exercises librosa.load end-to-end.
"""

from __future__ import annotations

import io
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import app.services.cache as cache_mod
import app.services.pronunciation_cache as pron_cache
from app.main import app
from app.models.shadow import PronunciationResult, PronunciationWord
from app.services.pronunciation import PronunciationServiceError

SR = 16000


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# WAV builders
# ---------------------------------------------------------------------------

def _sine(freq: float, duration_s: float, amplitude: float = 0.5) -> np.ndarray:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    return (amplitude * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)


def _silence(duration_s: float) -> np.ndarray:
    return np.zeros(int(SR * duration_s), dtype=np.float32)


def _wav_bytes(audio: np.ndarray) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, audio, SR, format="WAV")
    return buf.getvalue()


def _tone_wav(duration_s: float = 1.5) -> bytes:
    return _wav_bytes(_sine(440.0, duration_s))


# ---------------------------------------------------------------------------
# Happy path — uploaded target
# ---------------------------------------------------------------------------

def test_analyze_returns_shadow_analysis(client):
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert set(data.keys()) == {"prosody", "pronunciation", "pronunciation_error"}
    # No Azure creds supplied → pronunciation is null and no error.
    assert data["pronunciation"] is None
    assert data["pronunciation_error"] is None
    prosody = data["prosody"]
    assert "target" in prosody and "learner" in prosody
    assert "pace_match_score" in prosody and "tips" in prosody
    assert 0.0 <= prosody["pace_match_score"] <= 100.0
    assert isinstance(prosody["tips"], list) and len(prosody["tips"]) >= 1
    # Identical clips → very high score.
    assert prosody["pace_match_score"] > 90.0


def test_analyze_faster_learner_gets_faster_tip(client):
    target_bytes = _tone_wav(2.0)
    learner_bytes = _tone_wav(1.4)  # 30% faster

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 200
    prosody = resp.json()["prosody"]
    joined = " ".join(prosody["tips"]).lower()
    assert "faster" in joined
    assert prosody["pace_match_score"] < 90.0


def test_analyze_reports_prosody_features(client):
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 200
    prosody = resp.json()["prosody"]
    for side in ("target", "learner"):
        pf = prosody[side]
        assert pf["duration_s"] == pytest.approx(1.5, abs=0.05)
        assert pf["speaking_rate"] >= 0
        assert pf["pause_count"] == 0
        assert pf["pause_positions_s"] == []


# ---------------------------------------------------------------------------
# Target sourcing
# ---------------------------------------------------------------------------

def test_analyze_accepts_target_from_cache(client, isolated_cache):
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)

    key = cache_mod.make_key("hello", "en", "fish-en-001", 1.0)
    cache_mod.put(key, target_bytes, {"total_ms": 1500, "entries": []})

    resp = client.post(
        "/api/shadow/analyze",
        files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
        data={"target_cache_key": key},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["prosody"]["pace_match_score"] > 90.0


def test_analyze_requires_a_target(client):
    learner_bytes = _tone_wav(1.5)
    resp = client.post(
        "/api/shadow/analyze",
        files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
    )
    assert resp.status_code == 422
    assert "target" in resp.json()["detail"].lower()


def test_analyze_rejects_both_target_sources(client):
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)
    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
        data={"target_cache_key": "somekey"},
    )
    assert resp.status_code == 422


def test_analyze_unknown_cache_key_returns_404(client):
    learner_bytes = _tone_wav(1.5)
    resp = client.post(
        "/api/shadow/analyze",
        files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
        data={"target_cache_key": "deadbeef" * 8},
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Duration cap
# ---------------------------------------------------------------------------

def test_analyze_rejects_learner_over_duration_cap(client):
    target_bytes = _tone_wav(1.5)
    # 31 s > 30 s cap
    learner_bytes = _wav_bytes(_sine(440.0, 31.0))

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 413
    assert "cap" in resp.json()["detail"].lower()


def test_analyze_rejects_target_over_duration_cap(client):
    target_bytes = _wav_bytes(_sine(440.0, 31.0))
    learner_bytes = _tone_wav(1.5)

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 413


# ---------------------------------------------------------------------------
# Empty / undecodable input
# ---------------------------------------------------------------------------

def test_analyze_rejects_empty_learner(client):
    target_bytes = _tone_wav(1.5)
    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", b"", "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 422


def test_analyze_rejects_undecodable_audio(client):
    target_bytes = _tone_wav(1.5)
    junk = b"not-audio-bytes" * 10
    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.bin", junk, "application/octet-stream"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Language-agnostic: no language field required or accepted
# ---------------------------------------------------------------------------

def test_analyze_does_not_require_language(client):
    """Prosodic comparison is one code path for all languages — no language
    field on the request. Sanity check that the endpoint works without one."""
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)

    resp = client.post(
        "/api/shadow/analyze",
        files={
            "learner": ("learner.wav", learner_bytes, "audio/wav"),
            "target": ("target.wav", target_bytes, "audio/wav"),
        },
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Pronunciation integration — the service is mocked; we assert on
# orchestration (headers → call, cache hit skips call, absent key → null).
# ---------------------------------------------------------------------------

def _sample_pronunciation_result() -> PronunciationResult:
    return PronunciationResult(
        overall_score=88.0,
        words=[
            PronunciationWord(text="hello", accuracy_score=95.0, status="correct"),
            PronunciationWord(text="world", accuracy_score=70.0, status="mispronounced"),
        ],
    )


def _prime_synth_cache(text: str = "hello world", language: str = "en") -> str:
    """Put a fake target clip in the synth cache and return its key."""
    key = cache_mod.make_key(text, language, "fish-en-001", 1.0)
    cache_mod.put(key, _tone_wav(1.5), {"total_ms": 1500, "entries": [], "language": language})
    return key


# --- key-present path ------------------------------------------------------

def test_analyze_calls_pronunciation_when_azure_headers_present(client):
    target_key = _prime_synth_cache()
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(return_value=_sample_pronunciation_result())

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={
                "target_cache_key": target_key,
                "target_text": "hello world",
                "language": "en",
            },
            headers={
                "X-Azure-Speech-Key": "test-azure-key",
                "X-Azure-Speech-Region": "westus",
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prosody"]["pace_match_score"] > 90.0
    assert body["pronunciation"] is not None
    assert body["pronunciation"]["overall_score"] == 88.0
    assert [w["text"] for w in body["pronunciation"]["words"]] == ["hello", "world"]
    # Happy path — no error field set.
    assert body.get("pronunciation_error") is None

    # Service was called exactly once, with the caller's key/region.
    mock_score.assert_awaited_once()
    kwargs = mock_score.await_args.kwargs
    assert kwargs["key"] == "test-azure-key"
    assert kwargs["region"] == "westus"
    assert kwargs["target_text"] == "hello world"


# --- key-absent path -------------------------------------------------------

def test_analyze_returns_null_pronunciation_when_azure_key_missing(client):
    target_bytes = _tone_wav(1.5)
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(side_effect=AssertionError("Azure must not be called"))

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        resp = client.post(
            "/api/shadow/analyze",
            files={
                "learner": ("learner.wav", learner_bytes, "audio/wav"),
                "target": ("target.wav", target_bytes, "audio/wav"),
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["pronunciation"] is None
    # Prosody still populated — Independence contract.
    assert body["prosody"]["pace_match_score"] > 90.0
    mock_score.assert_not_awaited()


def test_analyze_returns_null_pronunciation_when_region_missing(client):
    """Key alone is not enough — region must also be present."""
    target_key = _prime_synth_cache()
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(side_effect=AssertionError("Azure must not be called"))

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={
                "target_cache_key": target_key,
                "target_text": "hello world",
                "language": "en",
            },
            headers={"X-Azure-Speech-Key": "test-azure-key"},
        )

    assert resp.status_code == 200
    assert resp.json()["pronunciation"] is None
    mock_score.assert_not_awaited()


# --- cache-hit path --------------------------------------------------------

def test_analyze_cache_hit_skips_pronunciation_call(client):
    """Second identical request must hit the pronunciation cache — the
    service must not be called again."""
    target_key = _prime_synth_cache()
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(return_value=_sample_pronunciation_result())

    request_kwargs = dict(
        files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
        data={
            "target_cache_key": target_key,
            "target_text": "hello world",
            "language": "en",
        },
        headers={
            "X-Azure-Speech-Key": "test-azure-key",
            "X-Azure-Speech-Region": "westus",
        },
    )

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        first = client.post("/api/shadow/analyze", **request_kwargs)
        second = client.post("/api/shadow/analyze", **request_kwargs)

    assert first.status_code == 200 and second.status_code == 200
    # Identical body on both requests.
    assert first.json()["pronunciation"] == second.json()["pronunciation"]
    # Azure was called exactly once — the second call was served from cache.
    assert mock_score.await_count == 1

    # And the cache file was actually written (JSON only — see pron_cache tests).
    learner_hash = pron_cache.hash_audio(learner_bytes)
    assert pron_cache.exists(pron_cache.make_key(target_key, learner_hash))


# --- Pronunciation-service failure degrades gracefully (Independence) -------

def test_analyze_pronunciation_error_returns_prosody_and_error_message(client):
    """When Azure fails, the whole request must still succeed and return
    prosody. The pronunciation block is null and pronunciation_error carries
    a client-safe message. See CLAUDE.md "Independence"."""
    target_key = _prime_synth_cache()
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(
        side_effect=PronunciationServiceError(
            status_code=502, detail="Azure Speech API returned HTTP 500."
        )
    )

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={
                "target_cache_key": target_key,
                "target_text": "hello world",
                "language": "en",
            },
            headers={
                "X-Azure-Speech-Key": "test-azure-key",
                "X-Azure-Speech-Region": "westus",
            },
        )

    # Whole request succeeds despite the pronunciation failure.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prosody"]["pace_match_score"] > 90.0
    assert body["pronunciation"] is None
    assert body["pronunciation_error"] == "Azure Speech API returned HTTP 500."
    mock_score.assert_awaited_once()

    # And nothing gets cached when Azure fails — cache write only happens on
    # a successful result.
    learner_hash = pron_cache.hash_audio(learner_bytes)
    assert not pron_cache.exists(pron_cache.make_key(target_key, learner_hash))


# --- 422 when Azure creds present but reference inputs missing --------------

def test_analyze_azure_headers_without_target_text_is_422(client):
    target_key = _prime_synth_cache()
    learner_bytes = _tone_wav(1.5)
    mock_score = AsyncMock(side_effect=AssertionError("Azure must not be called"))

    with patch("app.routers.shadow.pronunciation_service.score", mock_score):
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={"target_cache_key": target_key, "language": "en"},
            headers={
                "X-Azure-Speech-Key": "test-azure-key",
                "X-Azure-Speech-Region": "westus",
            },
        )

    assert resp.status_code == 422
    assert "target_text" in resp.json()["detail"]
    mock_score.assert_not_awaited()
