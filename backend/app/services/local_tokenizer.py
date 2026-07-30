"""Deterministic word tokenizer for Spanish and English.

No network calls, no external dependencies beyond the stdlib re module.
Returns the same list[Token] shape as the OpenAI segmenter so downstream
code is language-blind.

Design notes
------------
- Unicode letter runs are the core "word" unit.  The character class
  [^not-word, not-digit, not-underscore] is used so that digits and
  underscores don't silently join onto a word.
- Apostrophe/right-single-quote merging keeps English contractions (don't,
  it's, I'm, we'll) and French-style elisions as single tokens.
- Punctuation (including Spanish ¿/¡, ellipsis, dashes) is emitted as its
  own token so the timing allocator can insert pause dwell there.
- Whitespace is consumed but never emitted.
"""

import re

from app.models.language import Language
from app.models.token import Token

# Order matters: try word-with-contraction first, then number, then punctuation.
_TOKEN_RE = re.compile(
    r"[^\W\d_]+(?:['’][^\W\d_]+)*"  # letters + optional 'contraction suffix
    r"|\d+"                                 # digit runs (e.g. "500")
    r"|[^\w\s]",                            # any non-word, non-space char (punctuation)
    re.UNICODE,
)


def segment(text: str, language: Language) -> list[Token]:  # noqa: ARG001
    """Tokenise *text* for Spanish or English.

    ``language`` is accepted so the signature is uniform, but the logic is
    identical for both — the caller (segmenter.py) guarantees this is never
    called for ``zh``.
    """
    tokens: list[Token] = []
    for idx, m in enumerate(_TOKEN_RE.finditer(text)):
        tokens.append(
            Token(
                text=m.group(),
                index=idx,
                start=m.start(),
                end=m.end(),
            )
        )
    return tokens
