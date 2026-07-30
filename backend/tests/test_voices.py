import pytest

from app.models.language import Language
from app.voices import CATALOG, get_voice, list_voices


# --- catalog shape ---

def test_catalog_has_two_voices_per_language():
    for lang in Language:
        assert len(list_voices(lang)) == 2, f"Expected 2 voices for {lang.value}"


def test_all_voices_have_unique_reference_ids():
    ids = [v.reference_id for v in CATALOG]
    assert len(ids) == len(set(ids))


# --- list_voices filter ---

def test_list_voices_no_filter_returns_all():
    assert len(list_voices()) == len(CATALOG)


def test_list_voices_zh_returns_only_zh():
    voices = list_voices(Language.ZH)
    assert all(v.language == Language.ZH for v in voices)


def test_list_voices_es_returns_only_es():
    voices = list_voices(Language.ES)
    assert all(v.language == Language.ES for v in voices)


def test_list_voices_en_returns_only_en():
    voices = list_voices(Language.EN)
    assert all(v.language == Language.EN for v in voices)


# --- get_voice ---

def test_get_voice_returns_voice_for_known_id():
    voice = CATALOG[0]
    assert get_voice(voice.reference_id) == voice


def test_get_voice_returns_none_for_unknown_id():
    assert get_voice("does-not-exist") is None


# --- validate_voice_for_language ---

from fastapi import HTTPException
from app.services.voice_validator import validate_voice_for_language


def test_validate_accepts_matching_language():
    zh_voice = list_voices(Language.ZH)[0]
    result = validate_voice_for_language(zh_voice.reference_id, Language.ZH)
    assert result == zh_voice


def test_validate_raises_404_for_unknown_voice():
    with pytest.raises(HTTPException) as exc:
        validate_voice_for_language("ghost-voice", Language.EN)
    assert exc.value.status_code == 404


def test_validate_raises_422_for_language_mismatch():
    zh_voice = list_voices(Language.ZH)[0]
    with pytest.raises(HTTPException) as exc:
        validate_voice_for_language(zh_voice.reference_id, Language.ES)
    assert exc.value.status_code == 422
    assert "zh" in exc.value.detail
    assert "es" in exc.value.detail
