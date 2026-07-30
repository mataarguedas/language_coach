from typing import Literal

from pydantic import BaseModel, Field

PronunciationStatus = Literal["correct", "mispronounced", "omitted", "inserted"]


class ProsodyFeatures(BaseModel):
    duration_s: float = Field(ge=0)
    speaking_rate: float = Field(ge=0, description="Voiced-frames per second.")
    pause_count: int = Field(ge=0)
    pause_positions_s: list[float]


class ProsodyBlock(BaseModel):
    """Language-agnostic prosodic comparison of target vs learner."""

    target: ProsodyFeatures
    learner: ProsodyFeatures
    pace_match_score: float = Field(ge=0, le=100)
    tips: list[str]


class PronunciationWord(BaseModel):
    text: str
    accuracy_score: float = Field(ge=0, le=100)
    status: PronunciationStatus


class PronunciationResult(BaseModel):
    """Word-level pronunciation scores from a hosted assessment provider.

    MVP scope: overall score + per-word scores. Providers return per-phoneme
    data too; it is deliberately excluded here so the frontend cannot depend
    on it before a phoneme drill-down is scoped.
    """

    overall_score: float = Field(ge=0, le=100)
    words: list[PronunciationWord]


class ShadowAnalysis(BaseModel):
    """Envelope returned by /shadow/analyze.

    Prosody always runs. Pronunciation is a strict opt-in — absent when the
    caller did not supply an Azure Speech key, absent-with-message when
    Azure was invoked but failed (Independence: never fail the whole request
    because pronunciation is unavailable).
    """

    prosody: ProsodyBlock
    pronunciation: PronunciationResult | None = None
    # Populated when Azure was invoked but produced an error. Human-readable,
    # safe to display; never contains the subscription key.
    pronunciation_error: str | None = None
