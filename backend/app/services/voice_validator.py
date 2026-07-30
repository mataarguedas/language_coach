from fastapi import HTTPException

from app.models.language import Language
from app.models.voice import Voice
from app.voices import get_voice


def validate_voice_for_language(voice_id: str, language: Language) -> Voice:
    """Return the Voice if it exists and belongs to `language`; raise 4xx otherwise."""
    voice = get_voice(voice_id)
    if voice is None:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_id}' not found.")
    if voice.language != language:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Voice '{voice_id}' is a {voice.language.value} voice "
                f"but the request language is {language.value}."
            ),
        )
    return voice
