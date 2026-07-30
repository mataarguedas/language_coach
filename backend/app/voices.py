from app.models.language import Language
from app.models.voice import Voice

CATALOG: list[Voice] = [
    # Mandarin
    Voice(
        reference_id="5bbf057d30974e8ca39f3bb0a0c0c88f",
        label="Mandarin — Mei (Female)",
        language=Language.ZH,
        sample_url=None,
    ),
    Voice(
        reference_id="974cff79957e4b96b13256d90df4ff11",
        label="Mandarin — Wei (Male)",
        language=Language.ZH,
        sample_url=None,
    ),
    # Spanish
    Voice(
        reference_id="e296306da5d449999f6e35c2b9f60aea",
        label="Spanish — Sofía (Female)",
        language=Language.ES,
        sample_url=None,
    ),
    Voice(
        reference_id="dde221b4567a41faa3bfa79ddbb53e44",
        label="Spanish — Carlos (Male)",
        language=Language.ES,
        sample_url=None,
    ),
    # English
    Voice(
        reference_id="933563129e564b19a115bedd57b7406a",
        label="Sarah",
        language=Language.EN,
        sample_url=None,
    ),
    Voice(
        reference_id="ac6474da3a324e0c8edf6d796fe59f4d",
        label="Wheatley",
        language=Language.EN,
        sample_url=None,
    ),
]

_by_id: dict[str, Voice] = {v.reference_id: v for v in CATALOG}


def list_voices(language: Language | None = None) -> list[Voice]:
    if language is None:
        return list(CATALOG)
    return [v for v in CATALOG if v.language == language]


def get_voice(reference_id: str) -> Voice | None:
    return _by_id.get(reference_id)
