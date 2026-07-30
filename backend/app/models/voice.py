from pydantic import BaseModel

from app.models.language import Language


class Voice(BaseModel):
    reference_id: str
    label: str
    language: Language
    sample_url: str | None = None
