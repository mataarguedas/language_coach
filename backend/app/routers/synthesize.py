import io

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response

import app.services.cache as cache_mod
import app.services.timing as timing_mod
from app.models.synthesize import (
    SynthesizeRequest,
    SynthesizeResponse,
    TimingEntry,
    TimingSchedule,
)
from app.services.fish import SPEED_PRESETS, synthesize as fish_synthesize
from app.services.segmenter import segment as segmenter_segment
from app.services.voice_validator import validate_voice_for_language

MAX_TEXT_CHARS = 500

router = APIRouter()


def _mp3_duration_ms(audio_bytes: bytes) -> int:
    """Return the duration of *audio_bytes* (MP3) in milliseconds.

    Falls back to 0 if the bytes cannot be parsed (e.g. in tests with fake data).
    """
    try:
        from mutagen.mp3 import MP3

        return int(MP3(io.BytesIO(audio_bytes)).info.length * 1000)
    except Exception:
        return 0


@router.post("/synthesize", response_model=SynthesizeResponse)
async def synthesize(
    req: SynthesizeRequest,
    x_fish_key: str | None = Header(default=None),
    x_openai_key: str | None = Header(default=None),
) -> SynthesizeResponse:
    """Synthesise *text* via Fish Audio and return audio URL + karaoke timing.

    ``X-OpenAI-Key`` is only required when ``language`` is ``zh``; Spanish and
    English requests succeed without it.
    """
    if not x_fish_key:
        raise HTTPException(
            status_code=422,
            detail="X-Fish-Key header is required for synthesis.",
        )

    if len(req.text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"Text exceeds the {MAX_TEXT_CHARS}-character limit ({len(req.text)} chars supplied).",
        )

    if req.speed not in SPEED_PRESETS:
        raise HTTPException(
            status_code=422,
            detail=f"Speed {req.speed!r} is not a valid preset. Use one of {sorted(SPEED_PRESETS)}.",
        )

    # Raises 404/422 if voice is unknown or belongs to a different language.
    validate_voice_for_language(req.voice_id, req.language)

    cache_key = cache_mod.make_key(
        req.text, req.language.value, req.voice_id, req.speed
    )

    entry = cache_mod.get(cache_key)
    if entry is not None:
        meta = entry.meta
    else:
        # Segment first so a missing zh key fails before we spend a Fish call.
        tokens = await segmenter_segment(req.text, req.language, x_openai_key)

        audio_bytes = await fish_synthesize(req.text, req.voice_id, req.speed, x_fish_key)

        total_ms = _mp3_duration_ms(audio_bytes)
        timing_entries = timing_mod.allocate(tokens, total_ms)

        meta = {
            "total_ms": total_ms,
            "entries": [e.model_dump() for e in timing_entries],
            "language": req.language.value,
            "voice_id": req.voice_id,
            "speed": req.speed,
        }
        cache_mod.put(cache_key, audio_bytes, meta)

    timing = TimingSchedule(
        total_ms=meta.get("total_ms", 0),
        entries=[TimingEntry.model_validate(e) for e in meta.get("entries", [])],
    )

    return SynthesizeResponse(
        language=req.language,
        voice_id=req.voice_id,
        speed=req.speed,
        cache_key=cache_key,
        audio_url=f"/api/synthesize/audio/{cache_key}",
        timing=timing,
    )


@router.get("/synthesize/audio/{cache_key}")
async def get_audio(cache_key: str) -> Response:
    """Serve a cached MP3 by its content-addressable key."""
    entry = cache_mod.get(cache_key)
    if entry is None:
        raise HTTPException(status_code=404, detail="Audio not found in cache.")
    return Response(content=entry.audio, media_type="audio/mpeg")
