from app.models import Language


def test_language_has_exactly_three_members():
    assert len(list(Language)) == 3


def test_language_values_are_zh_es_en():
    assert {m.value for m in Language} == {"zh", "es", "en"}
