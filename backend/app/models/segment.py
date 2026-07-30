from pydantic import BaseModel, Field

from app.models.language import Language
from app.models.token import Token


class SegmentRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Language


class SegmentResponse(BaseModel):
    language: Language
    tokens: list[Token]
