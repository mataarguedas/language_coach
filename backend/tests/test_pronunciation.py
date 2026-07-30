"""Unit tests for the Azure Pronunciation Assessment client.

All HTTP is intercepted with :class:`httpx.MockTransport` — no real network
calls. Per-language tests assert that:
  * the request URL carries the correct region host and locale query,
  * the pronunciation-assessment header decodes to a Word-granularity config
    referencing the caller's target text,
  * the subscription key rides in the Ocp-Apim-Subscription-Key header,
  * a well-formed Azure response round-trips into a PronunciationResult.

One malformed-response test locks in the "clean typed error, no traceback"
contract.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import httpx
import pytest

from app.models.language import Language
from app.models.shadow import PronunciationResult
from app.services.pronunciation import (
    PronunciationServiceError,
    score,
)


# ---------------------------------------------------------------------------
# Helpers: canned Azure success bodies + transport injection
# ---------------------------------------------------------------------------

def _word(text: str, accuracy: float, error_type: str = "None") -> dict:
    return {
        "Word": text,
        # Phoneme data is present on real Azure responses; include some here
        # to prove the module ignores it (MVP: word-level only).
        "Phonemes": [
            {"Phoneme": "h", "PronunciationAssessment": {"AccuracyScore": 90.0}},
        ],
        "PronunciationAssessment": {
            "AccuracyScore": accuracy,
            "ErrorType": error_type,
        },
    }


def _azure_success_body(overall: float, words: list[dict]) -> dict:
    return {
        "RecognitionStatus": "Success",
        "DisplayText": " ".join(w["Word"] for w in words),
        "NBest": [
            {
                "PronunciationAssessment": {
                    "AccuracyScore": overall,
                    "FluencyScore": 80.0,
                    "CompletenessScore": 100.0,
                    "PronScore": overall,
                },
                "Words": words,
            }
        ],
    }


def _install_transport(handler):
    """Patch httpx.AsyncClient inside pronunciation.py to route through a
    MockTransport. Preserves the module's own timeout/kwargs."""
    transport = httpx.MockTransport(handler)
    real_cls = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return real_cls(*args, **kwargs)

    return patch("app.services.pronunciation.httpx.AsyncClient", factory)


def _decode_assessment_header(header_value: str) -> dict:
    return json.loads(base64.b64decode(header_value).decode("utf-8"))


# ---------------------------------------------------------------------------
# Per-language happy paths — locale must land in URL and the request must
# carry the caller's key + assessment header.
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("language", "region", "target_text", "expected_locale"),
    [
        (Language.ZH, "eastasia", "你好世界", "zh-CN"),
        (Language.ES, "westeurope", "hola mundo", "es-ES"),
        (Language.EN, "westus", "hello world", "en-US"),
    ],
)
async def test_locale_reaches_url_and_header(
    language, region, target_text, expected_locale
):
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["content"] = request.content
        body = _azure_success_body(
            overall=87.5,
            words=[_word(target_text, 90.0)],
        )
        return httpx.Response(200, json=body)

    with _install_transport(handler):
        result = await score(
            audio_bytes=b"fake-wav-bytes",
            target_text=target_text,
            language=language,
            key="my-secret-key",
            region=region,
        )

    # Region lives in the host, locale lives in the query string.
    assert f"{region}.stt.speech.microsoft.com" in captured["url"]
    assert f"language={expected_locale}" in captured["url"]
    assert captured["method"] == "POST"

    # Key must ride in the Azure header, never in the URL.
    assert captured["headers"]["ocp-apim-subscription-key"] == "my-secret-key"
    assert "my-secret-key" not in captured["url"]

    # Assessment header: Word granularity, reference = target_text, no phoneme output.
    config = _decode_assessment_header(captured["headers"]["pronunciation-assessment"])
    assert config["Granularity"] == "Word"
    assert config["ReferenceText"] == target_text
    assert "Phoneme" not in config["Granularity"]

    # Audio bytes are POSTed verbatim.
    assert captured["content"] == b"fake-wav-bytes"

    # Parsed round-trip.
    assert isinstance(result, PronunciationResult)
    assert result.overall_score == 87.5
    assert len(result.words) == 1
    assert result.words[0].text == target_text
    assert result.words[0].accuracy_score == 90.0
    assert result.words[0].status == "correct"


# ---------------------------------------------------------------------------
# Per-word status mapping — Azure ErrorType → MVP status set
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_word_error_types_map_to_status_set():
    words = [
        _word("hello", 95.0, "None"),
        _word("wurld", 40.0, "Mispronunciation"),
        _word("today", 0.0, "Omission"),
        _word("um", 0.0, "Insertion"),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_azure_success_body(70.0, words))

    with _install_transport(handler):
        result = await score(
            audio_bytes=b"x",
            target_text="hello world today",
            language=Language.EN,
            key="k",
            region="westus",
        )

    statuses = [w.status for w in result.words]
    assert statuses == ["correct", "mispronounced", "omitted", "inserted"]


# ---------------------------------------------------------------------------
# Phoneme fields on the wire must not appear on the returned model
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_phoneme_data_is_dropped():
    """MVP scope: the frontend must not be able to depend on per-phoneme
    scores. Even when Azure sends them, PronunciationWord has no phoneme
    field, so they cannot leak through."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json=_azure_success_body(90.0, [_word("hi", 95.0)])
        )

    with _install_transport(handler):
        result = await score(
            audio_bytes=b"x",
            target_text="hi",
            language=Language.EN,
            key="k",
            region="westus",
        )

    word = result.words[0]
    # PronunciationWord has exactly these fields — nothing phoneme-shaped.
    assert set(word.model_dump().keys()) == {"text", "accuracy_score", "status"}


# ---------------------------------------------------------------------------
# Malformed response — must raise a typed error, not a traceback
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_malformed_response_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        # 200 OK, but the payload is missing NBest entirely.
        return httpx.Response(200, json={"RecognitionStatus": "Success"})

    with _install_transport(handler):
        with pytest.raises(PronunciationServiceError) as excinfo:
            await score(
                audio_bytes=b"x",
                target_text="hello",
                language=Language.EN,
                key="k",
                region="westus",
            )

    assert excinfo.value.status_code == 502
    assert "parse" in excinfo.value.detail.lower()
    # Router-friendly: has a plain string detail, no key leaked.
    assert "k" not in excinfo.value.detail or "key" in excinfo.value.detail.lower()


@pytest.mark.asyncio
async def test_non_json_body_raises_typed_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>gateway error</html>")

    with _install_transport(handler):
        with pytest.raises(PronunciationServiceError) as excinfo:
            await score(
                audio_bytes=b"x",
                target_text="hello",
                language=Language.EN,
                key="k",
                region="westus",
            )

    assert excinfo.value.status_code == 502


# ---------------------------------------------------------------------------
# Non-2xx handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("upstream", "expected"),
    [(401, 401), (403, 401), (429, 429), (500, 502)],
)
async def test_upstream_status_maps_to_typed_error(upstream, expected):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(upstream, json={"error": "nope"})

    with _install_transport(handler):
        with pytest.raises(PronunciationServiceError) as excinfo:
            await score(
                audio_bytes=b"x",
                target_text="hello",
                language=Language.EN,
                key="secret",
                region="westus",
            )

    assert excinfo.value.status_code == expected
    # Key must never appear in the error detail.
    assert "secret" not in excinfo.value.detail


@pytest.mark.asyncio
async def test_recognition_status_not_success_raises_422():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"RecognitionStatus": "NoMatch"})

    with _install_transport(handler):
        with pytest.raises(PronunciationServiceError) as excinfo:
            await score(
                audio_bytes=b"x",
                target_text="hello",
                language=Language.EN,
                key="k",
                region="westus",
            )

    assert excinfo.value.status_code == 422
    assert "NoMatch" in excinfo.value.detail
