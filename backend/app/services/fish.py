"""Fish Audio hosted-API client.

Speed presets map 1-to-1 to Fish's prosody.speed parameter. Never use
client-side playbackRate — it distorts pitch.
"""

import httpx
from fastapi import HTTPException

FISH_TTS_URL = "https://api.fish.audio/v1/tts"

# Allowed discrete presets (shared across all languages).
SPEED_PRESETS: frozenset[float] = frozenset({0.7, 0.85, 1.0, 1.15})


async def synthesize(
    text: str,
    reference_id: str,
    speed: float,
    fish_key: str,
) -> bytes:
    """Call Fish TTS and return raw MP3 bytes.

    Raises HTTPException on invalid preset, bad key, or upstream error.
    Never logs or leaks the fish_key.
    """
    if speed not in SPEED_PRESETS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Speed {speed!r} is not a valid preset. "
                f"Use one of {sorted(SPEED_PRESETS)}."
            ),
        )

    payload = {
        "text": text,
        "reference_id": reference_id,
        "format": "mp3",
        "prosody": {"speed": speed},
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                FISH_TTS_URL,
                headers={"Authorization": f"Bearer {fish_key}"},
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Fish Audio API timed out. Check your network and retry.",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not reach Fish Audio API. Check your network and retry.",
        ) from exc

    if resp.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="Fish Audio API key is invalid or expired.",
        )
    if resp.status_code == 402:
        raise HTTPException(
            status_code=402,
            detail=(
                "Fish Audio account has insufficient credits. "
                "Top up your balance at https://fish.audio and try again."
            ),
        )
    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="Fish Audio rate limit exceeded. Try again shortly.",
        )
    if not resp.is_success:
        # Surface Fish's own error body so 400s from the upstream API are
        # diagnosable. Fish never echoes our Authorization header, so this
        # is safe.
        body = resp.text.strip()
        snippet = body[:300] if body else "(empty response body)"
        raise HTTPException(
            status_code=502,
            detail=(
                f"Fish Audio API returned HTTP {resp.status_code}: {snippet}"
            ),
        )

    return resp.content
