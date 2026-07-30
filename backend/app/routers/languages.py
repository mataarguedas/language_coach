from fastapi import APIRouter

from app.models.language_meta import LANGUAGE_META, LanguageMeta

router = APIRouter()


@router.get("/languages", response_model=list[LanguageMeta])
async def get_languages() -> list[LanguageMeta]:
    return LANGUAGE_META
