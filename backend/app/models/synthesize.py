from pydantic import BaseModel, Field

from app.models.language import Language
from app.models.token import Token


class SpeedPreset(BaseModel):
    """Discrete speed preset shared across languages; maps to Fish prosody params."""

    label: str
    value: float = Field(gt=0, description="Multiplier, e.g. 0.7, 0.85, 1.0, 1.15.")


class TimingEntry(BaseModel):
    token: Token
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)


class TimingSchedule(BaseModel):
    total_ms: int = Field(ge=0)
    entries: list[TimingEntry]


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1)
    language: Language
    voice_id: str
    speed: float = Field(gt=0, description="Discrete preset value (e.g. 1.0).")


class SynthesizeResponse(BaseModel):
    language: Language
    voice_id: str
    speed: float
    cache_key: str
    audio_url: str
    timing: TimingSchedule
