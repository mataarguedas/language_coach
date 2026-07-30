from pydantic import BaseModel, Field


class Token(BaseModel):
    text: str
    index: int = Field(ge=0)
    start: int = Field(ge=0, description="Character offset into the source text (inclusive).")
    end: int = Field(ge=0, description="Character offset into the source text (exclusive).")
