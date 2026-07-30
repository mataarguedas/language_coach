"""Language → Azure Speech locale mapping.

Pure, no I/O. Kept out of :mod:`app.services.pronunciation` so callers can
build a locale string without pulling in an HTTP client, and so the mapping
can be tested in isolation.

Azure Pronunciation Assessment is a single provider serving all three
languages; per-language behavior is a locale *parameter*, not a code branch
(see CLAUDE.md "Locked decisions"). This module is the only place that
mapping should live.
"""

from __future__ import annotations

from app.models.language import Language

_LOCALES: dict[Language, str] = {
    Language.ZH: "zh-CN",
    Language.ES: "es-ES",
    Language.EN: "en-US",
}


def to_azure_locale(language: Language) -> str:
    """Return the Azure Speech locale string for a supported language."""
    return _LOCALES[language]
