from fastapi import APIRouter, Header

from app.models.segment import SegmentRequest, SegmentResponse
from app.services import segmenter

router = APIRouter()


@router.post("/segment", response_model=SegmentResponse)
async def segment_text(
    req: SegmentRequest,
    x_openai_key: str | None = Header(default=None),
) -> SegmentResponse:
    """Segment *text* into an ordered token list.

    The OpenAI key header is only required when ``language`` is ``zh``.
    Spanish and English requests succeed without it.
    """
    tokens = await segmenter.segment(req.text, req.language, x_openai_key)
    return SegmentResponse(language=req.language, tokens=tokens)
