"""Tests for segmentation.

Guarantees that es/en NEVER touch the network and that the local tokenizer
handles the full range of Spanish/English surface forms correctly.
All OpenAI HTTP calls are mocked — the network is never hit.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.language import Language
from app.services import local_tokenizer, openai_seg, segmenter

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def words(tokens) -> list[str]:
    return [t.text for t in tokens]


def text_span(text: str, token) -> str:
    """Re-extract token text from source via its offsets — verifies start/end."""
    return text[token.start : token.end]


def _mock_openai_client(
    tokens: list[str] | None = None,
    status_code: int = 200,
) -> MagicMock:
    """Build an httpx.AsyncClient mock that returns a chat-completions response."""
    content = json.dumps({"tokens": tokens or []})
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.is_success = status_code < 400
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": content}}]
    }

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)
    return mock_client


# ---------------------------------------------------------------------------
# Local tokenizer — English fixtures
# ---------------------------------------------------------------------------

class TestEnglishTokenizer:
    def test_basic_words(self):
        ts = local_tokenizer.segment("Hello world", Language.EN)
        assert words(ts) == ["Hello", "world"]

    def test_contraction_dont(self):
        ts = local_tokenizer.segment("I don't know", Language.EN)
        assert "don't" in words(ts)
        # Must be a single token, not split into ["don", "'", "t"]
        assert "don" not in words(ts)

    def test_contraction_its(self):
        ts = local_tokenizer.segment("It's fine", Language.EN)
        assert "It's" in words(ts)

    def test_contraction_weve(self):
        ts = local_tokenizer.segment("We've arrived", Language.EN)
        assert "We've" in words(ts)

    def test_contraction_theyll(self):
        ts = local_tokenizer.segment("They'll come", Language.EN)
        assert "They'll" in words(ts)

    def test_contraction_im(self):
        ts = local_tokenizer.segment("I'm ready", Language.EN)
        assert "I'm" in words(ts)

    def test_punctuation_emitted(self):
        ts = local_tokenizer.segment("Hello, world!", Language.EN)
        assert "," in words(ts)
        assert "!" in words(ts)

    def test_period_emitted(self):
        ts = local_tokenizer.segment("Stop. Go.", Language.EN)
        assert words(ts).count(".") == 2

    def test_offsets_match_source(self):
        text = "Hello, world! It's great."
        for t in local_tokenizer.segment(text, Language.EN):
            assert text_span(text, t) == t.text, (
                f"Token {t.text!r}: text[{t.start}:{t.end}] = "
                f"{text_span(text, t)!r}"
            )

    def test_index_is_sequential(self):
        ts = local_tokenizer.segment("one two three", Language.EN)
        assert [t.index for t in ts] == list(range(len(ts)))

    def test_whitespace_not_emitted(self):
        ts = local_tokenizer.segment("a   b\tc", Language.EN)
        for t in ts:
            assert not t.text.isspace()

    def test_numbers(self):
        ts = local_tokenizer.segment("500 chars", Language.EN)
        assert "500" in words(ts)

    def test_empty_after_strip(self):
        ts = local_tokenizer.segment("   ", Language.EN)
        assert ts == []


# ---------------------------------------------------------------------------
# Local tokenizer — Spanish fixtures
# ---------------------------------------------------------------------------

class TestSpanishTokenizer:
    def test_accented_vowels(self):
        ts = local_tokenizer.segment("está aquí", Language.ES)
        assert "está" in words(ts)
        assert "aquí" in words(ts)

    def test_ene(self):
        ts = local_tokenizer.segment("El niño canta", Language.ES)
        assert "niño" in words(ts)

    def test_inverted_question(self):
        ts = local_tokenizer.segment("¿Cómo estás?", Language.ES)
        assert "¿" in words(ts)
        assert "Cómo" in words(ts)
        assert "estás" in words(ts)
        assert "?" in words(ts)

    def test_inverted_exclamation(self):
        ts = local_tokenizer.segment("¡Hola!", Language.ES)
        assert "¡" in words(ts)
        assert "Hola" in words(ts)
        assert "!" in words(ts)

    def test_multiple_accented(self):
        ts = local_tokenizer.segment("Él también habló", Language.ES)
        assert "Él" in words(ts)
        assert "también" in words(ts)
        assert "habló" in words(ts)

    def test_diaeresis(self):
        ts = local_tokenizer.segment("La cigüeña vuela", Language.ES)
        assert "cigüeña" in words(ts)

    def test_del_al_single_tokens(self):
        # "del" (de+el) and "al" (a+el) are orthographically single words.
        ts = local_tokenizer.segment("Vengo del mercado al pueblo", Language.ES)
        assert "del" in words(ts)
        assert "al" in words(ts)

    def test_verb_clitic_dámelo(self):
        ts = local_tokenizer.segment("Dámelo ahora", Language.ES)
        assert "Dámelo" in words(ts)

    def test_offsets_match_source(self):
        text = "¿Cómo estás tú, amigo?"
        for t in local_tokenizer.segment(text, Language.ES):
            assert text_span(text, t) == t.text

    def test_long_sentence(self):
        text = "La rápida zorra marrón saltó sobre el perro perezoso."
        ts = local_tokenizer.segment(text, Language.ES)
        assert len(ts) > 5
        for t in ts:
            assert text_span(text, t) == t.text


# ---------------------------------------------------------------------------
# OpenAI segmenter — unit tests (httpx mocked throughout)
# ---------------------------------------------------------------------------

class TestOpenAiSeg:
    @pytest.mark.anyio
    async def test_missing_key_raises_422(self):
        with pytest.raises(Exception) as exc_info:
            await openai_seg.segment("你好", openai_key=None)
        assert exc_info.value.status_code == 422
        assert "OpenAI" in exc_info.value.detail
        assert "Mandarin" in exc_info.value.detail

    @pytest.mark.anyio
    async def test_empty_key_raises_422(self):
        with pytest.raises(Exception) as exc_info:
            await openai_seg.segment("你好", openai_key="")
        assert exc_info.value.status_code == 422

    @pytest.mark.anyio
    async def test_happy_path_returns_llm_tokens(self):
        mock = _mock_openai_client(["你好", "世界"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment("你好世界", openai_key="sk-test")
        assert words(tokens) == ["你好", "世界"]

    @pytest.mark.anyio
    async def test_offsets_aligned_to_source(self):
        text = "我爱北京"
        mock = _mock_openai_client(["我", "爱", "北京"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment(text, openai_key="sk-test")
        assert words(tokens) == ["我", "爱", "北京"]
        for t in tokens:
            assert text[t.start : t.end] == t.text

    @pytest.mark.anyio
    async def test_gaps_in_source_handled(self):
        # LLM omits punctuation; the gap should not break offset alignment.
        text = "你好，世界"
        mock = _mock_openai_client(["你好", "世界"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment(text, openai_key="sk-test")
        assert words(tokens) == ["你好", "世界"]
        assert tokens[0].start == 0 and tokens[0].end == 2
        assert tokens[1].start == 3 and tokens[1].end == 5

    @pytest.mark.anyio
    async def test_traditional_characters(self):
        text = "電話學生"
        mock = _mock_openai_client(["電話", "學生"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment(text, openai_key="sk-test")
        assert words(tokens) == ["電話", "學生"]
        for t in tokens:
            assert text[t.start : t.end] == t.text

    @pytest.mark.anyio
    async def test_hallucinated_token_skipped(self):
        # "GHOST" does not appear in the source — should be silently dropped.
        text = "你好"
        mock = _mock_openai_client(["你好", "GHOST"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment(text, openai_key="sk-test")
        assert words(tokens) == ["你好"]

    @pytest.mark.anyio
    async def test_index_is_sequential(self):
        mock = _mock_openai_client(["我", "是", "学生"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            tokens = await openai_seg.segment("我是学生", openai_key="sk-test")
        assert [t.index for t in tokens] == list(range(len(tokens)))

    @pytest.mark.anyio
    async def test_authorization_header_sent(self):
        key = "sk-supersecret"
        mock = _mock_openai_client(["你好"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            await openai_seg.segment("你好", openai_key=key)
        call_kwargs = mock.post.call_args
        assert call_kwargs.kwargs["headers"]["Authorization"] == f"Bearer {key}"

    @pytest.mark.anyio
    async def test_invalid_key_raises_401(self):
        mock = _mock_openai_client(status_code=401)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            with pytest.raises(Exception) as exc_info:
                await openai_seg.segment("你好", openai_key="sk-bad")
        assert exc_info.value.status_code == 401

    @pytest.mark.anyio
    async def test_rate_limit_raises_429(self):
        mock = _mock_openai_client(status_code=429)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            with pytest.raises(Exception) as exc_info:
                await openai_seg.segment("你好", openai_key="sk-test")
        assert exc_info.value.status_code == 429

    @pytest.mark.anyio
    async def test_upstream_error_raises_502(self):
        mock = _mock_openai_client(status_code=500)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            with pytest.raises(Exception) as exc_info:
                await openai_seg.segment("你好", openai_key="sk-test")
        assert exc_info.value.status_code == 502

    @pytest.mark.anyio
    async def test_key_never_leaked_in_502_detail(self):
        key = "sk-supersecret-key"
        mock = _mock_openai_client(status_code=500)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            with pytest.raises(Exception) as exc_info:
                await openai_seg.segment("你好", openai_key=key)
        assert key not in exc_info.value.detail


# ---------------------------------------------------------------------------
# Dispatcher — es/en NEVER touch the network
# ---------------------------------------------------------------------------

class TestDispatchNoNetwork:
    """Prove es/en dispatch never reaches openai_seg by replacing it with a
    raising mock.  If the local tokenizer incorrectly calls through, the test
    will fail loudly."""

    @pytest.mark.anyio
    async def test_en_does_not_call_openai(self):
        mock = AsyncMock(side_effect=AssertionError("openai_seg must NOT be called for en"))
        with patch("app.services.segmenter.openai_seg.segment", mock):
            tokens = await segmenter.segment("Hello world", Language.EN)
        assert len(tokens) > 0
        mock.assert_not_called()

    @pytest.mark.anyio
    async def test_es_does_not_call_openai(self):
        mock = AsyncMock(side_effect=AssertionError("openai_seg must NOT be called for es"))
        with patch("app.services.segmenter.openai_seg.segment", mock):
            tokens = await segmenter.segment("Hola mundo", Language.ES)
        assert len(tokens) > 0
        mock.assert_not_called()

    @pytest.mark.anyio
    async def test_zh_calls_openai(self):
        mock = AsyncMock(return_value=[])
        with patch("app.services.segmenter.openai_seg.segment", mock):
            await segmenter.segment("你好", Language.ZH, openai_key="sk-test")
        mock.assert_awaited_once_with("你好", "sk-test")


# ---------------------------------------------------------------------------
# POST /api/segment — router integration
# ---------------------------------------------------------------------------

class TestSegmentRouter:
    def test_english_returns_tokens(self):
        resp = client.post(
            "/api/segment",
            json={"text": "Hello world", "language": "en"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "en"
        assert any(t["text"] == "Hello" for t in data["tokens"])
        assert any(t["text"] == "world" for t in data["tokens"])

    def test_spanish_returns_tokens(self):
        resp = client.post(
            "/api/segment",
            json={"text": "¿Cómo estás?", "language": "es"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["language"] == "es"
        texts = [t["text"] for t in data["tokens"]]
        assert "Cómo" in texts
        assert "estás" in texts

    def test_es_no_openai_key_still_works(self):
        """Spanish must not require an OpenAI key."""
        resp = client.post(
            "/api/segment",
            json={"text": "Hola mundo", "language": "es"},
        )
        assert resp.status_code == 200

    def test_en_no_openai_key_still_works(self):
        """English must not require an OpenAI key."""
        resp = client.post(
            "/api/segment",
            json={"text": "Hello", "language": "en"},
        )
        assert resp.status_code == 200

    def test_zh_missing_key_returns_422(self):
        resp = client.post(
            "/api/segment",
            json={"text": "你好世界", "language": "zh"},
        )
        assert resp.status_code == 422
        assert "OpenAI" in resp.json()["detail"]
        assert "Mandarin" in resp.json()["detail"]

    def test_zh_with_key_calls_llm_and_returns_tokens(self):
        """zh path calls OpenAI and surfaces the returned word-level tokens."""
        mock = _mock_openai_client(["你好", "世界"])
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            resp = client.post(
                "/api/segment",
                json={"text": "你好世界", "language": "zh"},
                headers={"X-OpenAI-Key": "sk-test-key"},
            )
        assert resp.status_code == 200
        data = resp.json()
        texts = [t["text"] for t in data["tokens"]]
        assert texts == ["你好", "世界"]
        mock.post.assert_awaited_once()

    def test_zh_invalid_key_returns_401(self):
        mock = _mock_openai_client(status_code=401)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            resp = client.post(
                "/api/segment",
                json={"text": "你好", "language": "zh"},
                headers={"X-OpenAI-Key": "sk-bad"},
            )
        assert resp.status_code == 401

    def test_zh_rate_limit_returns_429(self):
        mock = _mock_openai_client(status_code=429)
        with patch("app.services.openai_seg.httpx.AsyncClient", return_value=mock):
            resp = client.post(
                "/api/segment",
                json={"text": "你好", "language": "zh"},
                headers={"X-OpenAI-Key": "sk-test"},
            )
        assert resp.status_code == 429

    def test_token_shape(self):
        resp = client.post(
            "/api/segment",
            json={"text": "Hi there", "language": "en"},
        )
        assert resp.status_code == 200
        for t in resp.json()["tokens"]:
            assert "text" in t
            assert "index" in t
            assert "start" in t
            assert "end" in t
            assert t["start"] >= 0
            assert t["end"] > t["start"]

    def test_token_offsets_match_source(self):
        text = "don't stop"
        resp = client.post(
            "/api/segment",
            json={"text": text, "language": "en"},
        )
        assert resp.status_code == 200
        for t in resp.json()["tokens"]:
            assert text[t["start"] : t["end"]] == t["text"]

    def test_empty_text_rejected(self):
        resp = client.post(
            "/api/segment",
            json={"text": "", "language": "en"},
        )
        assert resp.status_code == 422  # pydantic min_length=1
