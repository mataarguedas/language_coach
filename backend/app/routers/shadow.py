"""Shadowing router — one round-trip returning prosody + optional pronunciation.

POST ``/api/shadow/analyze`` runs prosodic comparison *unconditionally* and
optionally scores per-word pronunciation via Azure Speech.

Independence (CLAUDE.md locked decision): prosody must succeed even when the
Azure key is absent. If ``X-Azure-Speech-Key`` or ``X-Azure-Speech-Region``
is missing, the response is ``{prosody, pronunciation: null}`` — never a
4xx. Azure is never called without the caller's opt-in.

Target reference sources (exactly one required):
  * multipart ``target`` file upload, or
  * form field ``target_cache_key`` referring to a previously synthesised clip.

Pronunciation additionally requires ``target_cache_key``, ``target_text``,
and ``language`` in the form body so Azure can be called in reference-scored
mode. Requests carrying Azure headers but omitting these are 422s — a caller
bug worth surfacing, not a silent skip.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import librosa
import numpy as np
from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

import app.services.cache as cache_mod
import app.services.pronunciation as pronunciation_service
import app.services.pronunciation_cache as pron_cache
from app.models.language import Language
from app.models.shadow import ProsodyBlock, PronunciationResult, ShadowAnalysis
from app.services.prosody import ProsodyResult, extract
from app.services.shadow_compare import compare, to_features

MAX_UPLOAD_DURATION_S = 30.0
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB hard byte cap; duration is the real limit
_LOAD_SR = 16000

router = APIRouter()


def _decode_and_extract(audio_bytes: bytes, *, source_name: str) -> ProsodyResult:
    """Decode arbitrary audio bytes, enforce the duration cap, extract prosody.

    Uses librosa (audioread/soundfile + ffmpeg) so WebM/Opus, MP3, WAV, etc.
    all work through the same path. Bytes are staged to a tempfile because
    librosa's decoders operate on file paths, not buffers.
    """
    if len(audio_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"{source_name} audio exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB byte cap."
            ),
        )

    tmp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".audio") as f:
            f.write(audio_bytes)
            tmp_path = Path(f.name)

        try:
            y, sr = librosa.load(str(tmp_path), sr=_LOAD_SR, mono=True)
        except Exception as exc:
            raise HTTPException(
                status_code=422,
                detail=f"Could not decode {source_name} audio: {exc}",
            ) from exc

        y = np.asarray(y, dtype=np.float32)
        duration = float(len(y) / sr) if sr else 0.0
        if duration > MAX_UPLOAD_DURATION_S:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"{source_name} audio is {duration:.1f}s, "
                    f"above the {MAX_UPLOAD_DURATION_S:.0f}s cap."
                ),
            )

        return extract(y, sr=sr)
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)


async def _maybe_score_pronunciation(
    *,
    learner_bytes: bytes,
    target_cache_key: str | None,
    target_text: str | None,
    language: Language | None,
    azure_key: str | None,
    azure_region: str | None,
) -> tuple[PronunciationResult | None, str | None]:
    """Return ``(result, error_message)`` for the pronunciation block.

    Contracts:
      * Strict opt-in — missing key OR region → ``(None, None)``, no 4xx.
      * Missing reference inputs alongside Azure creds is a real caller bug,
        so it still raises 422 (surface it, don't paper over).
      * Any :class:`PronunciationServiceError` from the Azure call is caught
        here and surfaced as ``error_message``. The whole request never
        fails because pronunciation is unavailable (CLAUDE.md
        "Independence") — prosody must still reach the client.
    """
    if not azure_key or not azure_region:
        return None, None

    missing = [
        name
        for name, value in (
            ("target_cache_key", target_cache_key),
            ("target_text", target_text),
            ("language", language),
        )
        if not value
    ]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=(
                "Pronunciation scoring requires "
                f"{', '.join(missing)} alongside the X-Azure-Speech-* headers."
            ),
        )

    # Hash in memory; the bytes go out of scope after this call — never disk.
    learner_hash = pron_cache.hash_audio(learner_bytes)
    cache_key = pron_cache.make_key(target_cache_key, learner_hash)  # type: ignore[arg-type]

    cached = pron_cache.get(cache_key)
    if cached is not None:
        return cached, None

    try:
        result = await pronunciation_service.score(
            audio_bytes=learner_bytes,
            target_text=target_text,  # type: ignore[arg-type]
            language=language,  # type: ignore[arg-type]
            key=azure_key,
            region=azure_region,
        )
    except pronunciation_service.PronunciationServiceError as exc:
        # Independence: Azure failed, but the request must not. Prosody is
        # already extracted and will be returned; the frontend gets a
        # user-friendly message on the pronunciation panel.
        return None, exc.detail

    pron_cache.put(cache_key, result)
    return result, None


@router.post("/analyze", response_model=ShadowAnalysis)
async def analyze(
    learner: UploadFile = File(..., description="Learner recording (WebM/Opus, WAV, MP3, …)."),
    target: UploadFile | None = File(
        default=None,
        description="Target reference audio. Provide this OR target_cache_key.",
    ),
    target_cache_key: str | None = Form(
        default=None,
        description="Cache key of a previously synthesised target clip.",
    ),
    target_text: str | None = Form(
        default=None,
        description="Reference text for pronunciation scoring (required for Azure).",
    ),
    language: Language | None = Form(
        default=None,
        description="Language code — required only for pronunciation scoring.",
    ),
    x_azure_speech_key: str | None = Header(default=None),
    x_azure_speech_region: str | None = Header(default=None),
) -> ShadowAnalysis:
    if (target is None) == (target_cache_key is None):
        raise HTTPException(
            status_code=422,
            detail="Provide exactly one of 'target' (upload) or 'target_cache_key'.",
        )

    learner_bytes = await learner.read()
    if not learner_bytes:
        raise HTTPException(status_code=422, detail="Learner audio is empty.")

    if target is not None:
        target_bytes = await target.read()
        if not target_bytes:
            raise HTTPException(status_code=422, detail="Target audio is empty.")
    else:
        entry = cache_mod.get(target_cache_key)  # type: ignore[arg-type]
        if entry is None:
            raise HTTPException(
                status_code=404,
                detail=f"target_cache_key {target_cache_key!r} not found in cache.",
            )
        target_bytes = entry.audio

    target_result = _decode_and_extract(target_bytes, source_name="target")
    learner_result = _decode_and_extract(learner_bytes, source_name="learner")

    score, tips = compare(target_result, learner_result)

    prosody = ProsodyBlock(
        target=to_features(target_result),
        learner=to_features(learner_result),
        pace_match_score=score,
        tips=tips,
    )

    pronunciation, pronunciation_error = await _maybe_score_pronunciation(
        learner_bytes=learner_bytes,
        target_cache_key=target_cache_key,
        target_text=target_text,
        language=language,
        azure_key=x_azure_speech_key,
        azure_region=x_azure_speech_region,
    )

    return ShadowAnalysis(
        prosody=prosody,
        pronunciation=pronunciation,
        pronunciation_error=pronunciation_error,
    )
