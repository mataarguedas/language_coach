"""OpenAI-backed word segmenter for Mandarin Chinese (zh).

Handles both Simplified and Traditional characters via a single
chat-completions call.  The key is read per-request and is never stored.

Error contract
--------------
- Missing key        → 422 (caller's fault, not a server error)
- Bad key (401)      → 401 forwarded
- Rate limit (429)   → 429 forwarded
- Any other failure  → 502 (upstream error)
"""

import json

import httpx
from fastapi import HTTPException

from app.models.token import Token

_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

_SYSTEM_PROMPT = """\
You are a Mandarin Chinese word segmenter that supports both Simplified and \
Traditional characters.

Given input text, return ONLY a JSON object in this exact format:
{"tokens": ["word1", "word2", ...]}

Rules:
- List tokens in the same left-to-right order as the source text.
- Each token must appear verbatim in the source (no translation, no romanisation, \
no character substitution).
- Group characters into natural words and phrases as a native Mandarin speaker \
would recognise — multi-character words (e.g. 学生, 電話) should be one token.
- Include punctuation that carries prosodic weight (。！？…、，；：); omit \
plain whitespace.
- Do not add tokens that are not in the source text.\
"""


async def segment(text: str, openai_key: str | None) -> list[Token]:
    """Segment Mandarin *text* into an ordered token list via the OpenAI API.

    Raises HTTPException 422 when no key is supplied — callers on the zh path
    must provide ``X-OpenAI-Key``.
    """
    if not openai_key:
        raise HTTPException(
            status_code=422,
            detail=(
                "An OpenAI API key is required for Mandarin segmentation. "
                "Please enter your key in the API Keys panel."
            ),
        )
    return await _call_openai(text, openai_key)


async def _call_openai(text: str, openai_key: str) -> list[Token]:
    payload = {
        "model": "gpt-4o-mini",
        "temperature": 0,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            _OPENAI_URL,
            headers={"Authorization": f"Bearer {openai_key}"},
            json=payload,
        )

    if resp.status_code == 401:
        raise HTTPException(
            status_code=401,
            detail="OpenAI API key is invalid or expired.",
        )
    if resp.status_code == 429:
        raise HTTPException(
            status_code=429,
            detail="OpenAI rate limit exceeded. Try again shortly.",
        )
    if not resp.is_success:
        raise HTTPException(
            status_code=502,
            detail=f"OpenAI API returned an unexpected error (HTTP {resp.status_code}).",
        )

    raw = resp.json()["choices"][0]["message"]["content"]
    word_list: list[str] = json.loads(raw)["tokens"]
    return _align_tokens(text, word_list)


def _align_tokens(text: str, words: list[str]) -> list[Token]:
    """Map LLM word strings back to character offsets in *text*.

    Uses a forward cursor so each word is matched at or after the previous
    match, preserving source order and handling gaps (e.g. whitespace the LLM
    omitted).  Tokens the LLM hallucinated (not found in text) are skipped.
    """
    tokens: list[Token] = []
    cursor = 0
    for word in words:
        pos = text.find(word, cursor)
        if pos == -1:
            continue  # hallucinated token — skip
        tokens.append(
            Token(
                text=word,
                index=len(tokens),
                start=pos,
                end=pos + len(word),
            )
        )
        cursor = pos + len(word)
    return tokens
