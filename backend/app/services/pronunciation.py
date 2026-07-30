"""Azure Speech Pronunciation Assessment client.

Pure I/O layer around Azure's REST endpoint. One integration serves all
three supported languages; per-language behavior is a locale *parameter*
built via :mod:`app.services.azure_locale`, never a code branch (see
CLAUDE.md "Locked decisions").

Scope: word-level scores only. Azure returns per-phoneme data on the wire;
this module deliberately never surfaces it, keeping the frontend from
depending on it before a phoneme drill-down is scoped.

Contract with the router:
  * Never logs the subscription key.
  * Never writes ``audio_bytes`` to disk — they enter, are POSTed, and go
    out of scope.
  * On any failure (transport, non-2xx, unparseable body, Azure's own
    non-Success recognition status) raises :class:`PronunciationServiceError`
    with an HTTP-appropriate ``status_code`` and a client-safe ``detail``
    (never containing the key).
"""

from __future__ import annotations

import base64
import json

import httpx

from app.models.language import Language
from app.models.shadow import (
    PronunciationResult,
    PronunciationStatus,
    PronunciationWord,
)
from app.services.azure_locale import to_azure_locale

# Azure's Word-level ErrorType → the MVP-restricted status set.
# Anything unrecognised falls back to "mispronounced" so novel error types
# never silently vanish from the user's word chips.
_AZURE_ERROR_TO_STATUS: dict[str, PronunciationStatus] = {
    "None": "correct",
    "Mispronunciation": "mispronounced",
    "Omission": "omitted",
    "Insertion": "inserted",
}

# The caller is expected to hand in 16 kHz mono PCM WAV bytes. Azure accepts
# other codecs via different Content-Type strings, but this module keeps the
# format contract narrow — audio conversion is the router's job.
_AUDIO_CONTENT_TYPE = "audio/wav; codecs=audio/pcm; samplerate=16000"
_TIMEOUT_S = 30.0


class PronunciationServiceError(Exception):
    """Typed error the router turns into a clean HTTPException.

    ``status_code`` is what the *API consumer* should see — not necessarily
    Azure's raw upstream code. ``detail`` is safe to include in the
    client-facing response; it never contains the subscription key.
    """

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _build_url(region: str, locale: str) -> str:
    return (
        f"https://{region}.stt.speech.microsoft.com/speech/recognition/"
        f"conversation/cognitiveservices/v1"
        f"?language={locale}&format=detailed"
    )


def _build_assessment_header(target_text: str) -> str:
    """Base64-encoded pronunciation-assessment configuration header value.

    Granularity is pinned to "Word" — phoneme data is out of MVP scope.
    """
    config = {
        "ReferenceText": target_text,
        "GradingSystem": "HundredMark",
        "Granularity": "Word",
        "Dimension": "Comprehensive",
        "EnableMiscue": True,
    }
    return base64.b64encode(json.dumps(config).encode("utf-8")).decode("ascii")


def _parse_response(body: dict) -> PronunciationResult:
    """Extract overall + per-word scores. Ignore any per-phoneme fields."""
    try:
        nbest = body["NBest"][0]
        overall = float(nbest["PronunciationAssessment"]["AccuracyScore"])
        raw_words = nbest["Words"]
        if not isinstance(raw_words, list):
            raise TypeError("Words must be a list")
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise PronunciationServiceError(
            status_code=502,
            detail="Azure returned a response we could not parse.",
        ) from exc

    words: list[PronunciationWord] = []
    for w in raw_words:
        try:
            text = w["Word"]
            assessment = w["PronunciationAssessment"]
            accuracy = float(assessment["AccuracyScore"])
            error_type = assessment.get("ErrorType", "None")
        except (KeyError, TypeError, ValueError) as exc:
            raise PronunciationServiceError(
                status_code=502,
                detail="Azure returned a word entry we could not parse.",
            ) from exc

        status = _AZURE_ERROR_TO_STATUS.get(error_type, "mispronounced")
        words.append(
            PronunciationWord(text=text, accuracy_score=accuracy, status=status)
        )

    return PronunciationResult(overall_score=overall, words=words)


async def score(
    audio_bytes: bytes,
    target_text: str,
    language: Language,
    key: str,
    region: str,
) -> PronunciationResult:
    """POST learner audio to Azure Pronunciation Assessment and parse.

    Reference-scored mode only — ``target_text`` is the string the user just
    synthesised, never a free-transcription request.
    """
    locale = to_azure_locale(language)
    url = _build_url(region, locale)
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": _AUDIO_CONTENT_TYPE,
        "Pronunciation-Assessment": _build_assessment_header(target_text),
        "Accept": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_S) as client:
            resp = await client.post(url, headers=headers, content=audio_bytes)
    except httpx.TimeoutException as exc:
        raise PronunciationServiceError(
            status_code=504,
            detail="Azure Speech API timed out.",
        ) from exc
    except httpx.RequestError as exc:
        raise PronunciationServiceError(
            status_code=502,
            detail="Could not reach Azure Speech API.",
        ) from exc

    if resp.status_code in (401, 403):
        raise PronunciationServiceError(
            status_code=401,
            detail="Azure Speech key or region is invalid.",
        )
    if resp.status_code == 429:
        raise PronunciationServiceError(
            status_code=429,
            detail="Azure Speech rate limit exceeded. Try again shortly.",
        )
    if not resp.is_success:
        raise PronunciationServiceError(
            status_code=502,
            detail=f"Azure Speech API returned HTTP {resp.status_code}.",
        )

    try:
        body = resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise PronunciationServiceError(
            status_code=502,
            detail="Azure Speech API returned a non-JSON body.",
        ) from exc

    # HTTP 200 with a non-Success recognition status means Azure ran but
    # couldn't score the utterance (e.g. NoMatch on silent audio).
    recognition_status = body.get("RecognitionStatus")
    if recognition_status is not None and recognition_status != "Success":
        raise PronunciationServiceError(
            status_code=422,
            detail=f"Azure could not recognise the audio (status={recognition_status!r}).",
        )

    return _parse_response(body)
