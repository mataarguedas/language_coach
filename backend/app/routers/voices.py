from fastapi import APIRouter

from app.models.language import Language
from app.models.voice import Voice
from app.voices import list_voices

router = APIRouter()


@router.get("/voices", response_model=list[Voice])
async def get_voices(language: Language | None = None) -> list[Voice]:
    return list_voices(language)
