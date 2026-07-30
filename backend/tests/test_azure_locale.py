"""Unit tests for the Language → Azure locale mapping.

Pure lookup — no HTTP, no fixtures. Locks the exact locale strings so an
accidental rename (e.g. en-US → en-GB) surfaces as a test failure rather
than a silent behavioral change in the pronunciation call.
"""

import pytest

from app.models.language import Language
from app.services.azure_locale import to_azure_locale


def test_mandarin_maps_to_zh_cn():
    assert to_azure_locale(Language.ZH) == "zh-CN"


def test_spanish_maps_to_es_es():
    assert to_azure_locale(Language.ES) == "es-ES"


def test_english_maps_to_en_us():
    assert to_azure_locale(Language.EN) == "en-US"


def test_mapping_covers_every_language():
    # Every Language enum member must have a locale — no silent KeyError
    # from a future fourth language.
    for lang in Language:
        assert isinstance(to_azure_locale(lang), str)


def test_unknown_input_raises_key_error():
    with pytest.raises(KeyError):
        to_azure_locale("fr")  # type: ignore[arg-type]
