"""Single dispatch point for text segmentation across all three languages.

Callers import only this module — they never call local_tokenizer or
openai_seg directly.  Both paths return ``list[Token]`` with the same shape
so timing/karaoke code is fully language-blind.

Dispatch:
  zh  → openai_seg.segment  (async, requires X-OpenAI-Key)
  es  → local_tokenizer.segment  (sync, no network)
  en  → local_tokenizer.segment  (sync, no network)
"""

from app.models.language import Language
from app.models.token import Token
from app.services import local_tokenizer, openai_seg


async def segment(
    text: str,
    language: Language,
    openai_key: str | None = None,
) -> list[Token]:
    """Segment *text* according to *language* and return an ordered token list.

    The ``openai_key`` is forwarded to the zh path; it is intentionally
    ignored for es/en so those paths never require an OpenAI key.
    """
    if language == Language.ZH:
        return await openai_seg.segment(text, openai_key)
    return local_tokenizer.segment(text, language)
