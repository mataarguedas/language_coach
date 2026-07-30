from pydantic import BaseModel

from app.models.language import Language


class LanguageMeta(BaseModel):
    code: Language
    label: str


LANGUAGE_META: list[LanguageMeta] = [
    LanguageMeta(code=Language.ZH, label="Mandarin"),
    LanguageMeta(code=Language.ES, label="Spanish"),
    LanguageMeta(code=Language.EN, label="English"),
]
