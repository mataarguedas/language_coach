"""End-to-end integration tests for /api/shadow/analyze.

Stitches together everything from prompts 1–4:
  * models / envelope shape           (prompt 1)
  * pronunciation cache               (prompt 2)
  * pronunciation.py Azure client     (prompt 3)
  * shadow router orchestration       (prompt 4)

Only the outbound HTTP layer is mocked — via :class:`httpx.MockTransport`
patched into the pronunciation service's ``httpx.AsyncClient``. Everything
above the socket (route dispatch, prosody extraction, header parsing,
cache read/write, response parsing, error mapping) runs for real.

Two invariants are asserted on every relevant test:
  * learner audio never appears on disk under ``CACHE_DIR`` (byte-equality
    walk of the whole tree), and
  * the Azure subscription key never appears in the response body, in any
    log record captured by ``caplog``, or in captured stdout/stderr.
"""

from __future__ import annotations

import io
import json
from unittest.mock import patch

import httpx
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import app.services.cache as cache_mod
import app.services.pronunciation_cache as pron_cache
from app.main import app

SR = 16000
AZURE_KEY = "SECRET-AZURE-KEY-do-not-leak-1234567890"
AZURE_REGION = "westus"
TARGET_TEXT = "hello world"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("CACHE_DIR", str(tmp_path))
    yield tmp_path


@pytest.fixture()
def client():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Audio helpers
# ---------------------------------------------------------------------------

def _sine_wav(duration_s: float = 1.5, freq: float = 440.0) -> bytes:
    t = np.linspace(0.0, duration_s, int(SR * duration_s), endpoint=False)
    y = (0.5 * np.sin(2.0 * np.pi * freq * t)).astype(np.float32)
    buf = io.BytesIO()
    sf.write(buf, y, SR, format="WAV")
    return buf.getvalue()


def _prime_target(text: str = TARGET_TEXT, language: str = "en") -> str:
    key = cache_mod.make_key(text, language, "fish-en-001", 1.0)
    cache_mod.put(key, _sine_wav(), {"total_ms": 1500, "entries": [], "language": language})
    return key


# ---------------------------------------------------------------------------
# Azure transport mocking
# ---------------------------------------------------------------------------

def _azure_success_body(overall: float = 88.0) -> dict:
    return {
        "RecognitionStatus": "Success",
        "DisplayText": "hello world",
        "NBest": [
            {
                "PronunciationAssessment": {"AccuracyScore": overall},
                "Words": [
                    {
                        "Word": "hello",
                        "PronunciationAssessment": {
                            "AccuracyScore": 95.0,
                            "ErrorType": "None",
                        },
                    },
                    {
                        "Word": "world",
                        "PronunciationAssessment": {
                            "AccuracyScore": 70.0,
                            "ErrorType": "Mispronunciation",
                        },
                    },
                ],
            }
        ],
    }


def _install_azure_transport(handler):
    """Patch httpx.AsyncClient inside pronunciation.py to route through a
    MockTransport running the caller's handler.

    Returns a context manager and the call-count list the handler should
    append to on each invocation (so tests can assert Azure was hit N times).
    """
    call_log: list[httpx.Request] = []

    def wrapped(request: httpx.Request) -> httpx.Response:
        call_log.append(request)
        return handler(request)

    transport = httpx.MockTransport(wrapped)
    real_cls = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_cls(*args, **kwargs)

    return patch("app.services.pronunciation.httpx.AsyncClient", factory), call_log


# ---------------------------------------------------------------------------
# Leak / invariant helpers
# ---------------------------------------------------------------------------

def _walk_files(root):
    return [p for p in root.rglob("*") if p.is_file()]


def _assert_learner_audio_not_on_disk(cache_root, learner_bytes: bytes) -> None:
    """No file anywhere under CACHE_DIR may contain the learner audio."""
    for p in _walk_files(cache_root):
        assert p.read_bytes() != learner_bytes, (
            f"Learner audio leaked to disk at {p}"
        )


def _assert_no_key_leak(*strings_to_scan: str) -> None:
    for s in strings_to_scan:
        assert AZURE_KEY not in s, "Azure key leaked into a captured string"


# ---------------------------------------------------------------------------
# 1. Full flow with Azure key present
# ---------------------------------------------------------------------------

def test_full_flow_with_azure_returns_both_blocks_and_no_learner_audio_on_disk(
    client, isolated_cache, caplog, capsys
):
    caplog.set_level("DEBUG")

    target_key = _prime_target()
    # Distinct frequency so the target's cached bytes can never coincidentally
    # match the learner's — the "no learner audio on disk" check depends on
    # byte-inequality between the two.
    learner_bytes = _sine_wav(freq=660.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_azure_success_body(overall=88.0))

    patcher, call_log = _install_azure_transport(handler)
    with patcher:
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={
                "target_cache_key": target_key,
                "target_text": TARGET_TEXT,
                "language": "en",
            },
            headers={
                "X-Azure-Speech-Key": AZURE_KEY,
                "X-Azure-Speech-Region": AZURE_REGION,
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Both blocks populated end-to-end.
    assert body["prosody"]["pace_match_score"] > 90.0
    assert body["pronunciation"]["overall_score"] == 88.0
    assert [w["text"] for w in body["pronunciation"]["words"]] == ["hello", "world"]
    assert [w["status"] for w in body["pronunciation"]["words"]] == [
        "correct",
        "mispronounced",
    ]

    # Azure was actually hit — this is a real HTTP round-trip through the
    # transport layer, not a stubbed service.
    assert len(call_log) == 1
    az_req = call_log[0]
    assert "language=en-US" in str(az_req.url)
    # Key rides in the header, never in the URL.
    assert AZURE_KEY not in str(az_req.url)
    assert az_req.headers["ocp-apim-subscription-key"] == AZURE_KEY

    # Pronunciation cache file exists (JSON only).
    learner_hash = pron_cache.hash_audio(learner_bytes)
    cache_key = pron_cache.make_key(target_key, learner_hash)
    assert pron_cache.exists(cache_key)
    pron_cache_dir = isolated_cache / "pronunciation"
    for f in _walk_files(pron_cache_dir):
        assert f.suffix == ".json", f"unexpected non-JSON file: {f}"

    # Learner audio is NOT on disk anywhere under the cache tree.
    _assert_learner_audio_not_on_disk(isolated_cache, learner_bytes)

    # Key must not leak into the response body, logs, or stdout/stderr.
    captured = capsys.readouterr()
    _assert_no_key_leak(
        resp.text,
        captured.out,
        captured.err,
        *(rec.getMessage() for rec in caplog.records),
    )


# ---------------------------------------------------------------------------
# 2. Full flow with Azure key absent
# ---------------------------------------------------------------------------

def test_full_flow_without_azure_returns_prosody_only_and_never_calls_azure(
    client, caplog
):
    caplog.set_level("DEBUG")
    target_bytes = _sine_wav()
    learner_bytes = _sine_wav()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("Azure must not be called without X-Azure-Speech-Key")

    patcher, call_log = _install_azure_transport(handler)
    with patcher:
        resp = client.post(
            "/api/shadow/analyze",
            files={
                "learner": ("learner.wav", learner_bytes, "audio/wav"),
                "target": ("target.wav", target_bytes, "audio/wav"),
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prosody"]["pace_match_score"] > 90.0
    assert body["pronunciation"] is None
    assert call_log == []


# ---------------------------------------------------------------------------
# 3. Malformed Azure response → prosody still returned, pronunciation null,
#    pronunciation_error populated. CLAUDE.md "Independence": never fail the
#    whole request because pronunciation is unavailable.
# ---------------------------------------------------------------------------

def test_malformed_azure_response_returns_prosody_with_error_message(
    client, isolated_cache, caplog, capsys
):
    caplog.set_level("DEBUG")
    target_key = _prime_target()
    # Distinct frequency so the target's cached bytes can never coincidentally
    # match the learner's — the "no learner audio on disk" check depends on
    # byte-inequality between the two.
    learner_bytes = _sine_wav(freq=660.0)

    def handler(request: httpx.Request) -> httpx.Response:
        # 200 OK but no NBest — pronunciation._parse_response can't parse.
        return httpx.Response(200, json={"RecognitionStatus": "Success"})

    patcher, _ = _install_azure_transport(handler)
    with patcher:
        resp = client.post(
            "/api/shadow/analyze",
            files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
            data={
                "target_cache_key": target_key,
                "target_text": TARGET_TEXT,
                "language": "en",
            },
            headers={
                "X-Azure-Speech-Key": AZURE_KEY,
                "X-Azure-Speech-Region": AZURE_REGION,
            },
        )

    # 200: the whole request succeeded even though Azure failed.
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # Prosody must be populated — Independence contract.
    assert body["prosody"]["pace_match_score"] > 90.0

    # Pronunciation degraded to null with an accompanying error message.
    assert body["pronunciation"] is None
    assert isinstance(body["pronunciation_error"], str)
    err = body["pronunciation_error"].lower()
    # Clean human-readable message — never a Python traceback.
    assert "traceback" not in err
    assert "  file \"" not in err
    assert "exception" not in err
    assert "parse" in err  # mirrors what pronunciation.py raises

    # No learner audio persisted despite the pronunciation failure.
    _assert_learner_audio_not_on_disk(isolated_cache, learner_bytes)

    # And nothing about the key in the response body or logs.
    captured = capsys.readouterr()
    _assert_no_key_leak(
        resp.text,
        captured.out,
        captured.err,
        *(rec.getMessage() for rec in caplog.records),
    )


# ---------------------------------------------------------------------------
# 4. Re-analysing the same (target, learner) pair hits the cache
# ---------------------------------------------------------------------------

def test_repeat_analysis_hits_cache_and_skips_azure(client, isolated_cache):
    target_key = _prime_target()
    # Distinct frequency so the target's cached bytes can never coincidentally
    # match the learner's — the "no learner audio on disk" check depends on
    # byte-inequality between the two.
    learner_bytes = _sine_wav(freq=660.0)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_azure_success_body(overall=88.0))

    request_kwargs = dict(
        files={"learner": ("learner.wav", learner_bytes, "audio/wav")},
        data={
            "target_cache_key": target_key,
            "target_text": TARGET_TEXT,
            "language": "en",
        },
        headers={
            "X-Azure-Speech-Key": AZURE_KEY,
            "X-Azure-Speech-Region": AZURE_REGION,
        },
    )

    patcher, call_log = _install_azure_transport(handler)
    with patcher:
        first = client.post("/api/shadow/analyze", **request_kwargs)
        second = client.post("/api/shadow/analyze", **request_kwargs)
        third = client.post("/api/shadow/analyze", **request_kwargs)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 200

    # Azure was called exactly once — the second and third served from cache.
    assert len(call_log) == 1

    # Bodies must be identical across all three responses.
    assert first.json()["pronunciation"] == second.json()["pronunciation"]
    assert second.json()["pronunciation"] == third.json()["pronunciation"]

    # And the cached payload on disk round-trips to the same result.
    learner_hash = pron_cache.hash_audio(learner_bytes)
    cached_path = isolated_cache / "pronunciation" / f"{pron_cache.make_key(target_key, learner_hash)}.json"
    cached = json.loads(cached_path.read_text())
    assert cached["overall_score"] == 88.0

    # Still no learner audio anywhere on disk.
    _assert_learner_audio_not_on_disk(isolated_cache, learner_bytes)
