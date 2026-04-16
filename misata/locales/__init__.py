"""
Locale-aware data generation for Misata.

Supports 15 locales with real statistical data:
  en_US, en_GB, de_DE, fr_FR, pt_BR, es_ES, hi_IN,
  ja_JP, zh_CN, ar_SA, ko_KR, nl_NL, it_IT, pl_PL, tr_TR

Usage::

    from misata.locales import detect_locale, get_locale_pack, LocaleRegistry

    locale = detect_locale("A German SaaS company in Berlin with 500 Mitarbeiter")
    # → "de_DE"

    pack = get_locale_pack("de_DE")
    print(pack.currency_symbol)   # €
    print(pack.salary_median)     # 45000
"""

from misata.locales.packs import LOCALE_PACKS, LocalePack
from misata.locales.detector import detect_locale_from_story, LOCALE_ALIASES
from misata.locales.registry import LocaleRegistry

DEFAULT_LOCALE = "en_US"


def detect_locale(story: str) -> str:
    """Detect locale from a plain-English story or description.

    Returns a BCP-47 locale code (e.g. ``"de_DE"``) or ``"en_US"`` if
    no locale-specific signal is found.

    Example::

        detect_locale("A Brazilian fintech with 1k users paying in R$")
        # → "pt_BR"
    """
    return detect_locale_from_story(story) or DEFAULT_LOCALE


def get_locale_pack(locale: str) -> "LocalePack":
    """Return the :class:`LocalePack` for *locale*, falling back to ``en_US``."""
    return LOCALE_PACKS.get(locale, LOCALE_PACKS[DEFAULT_LOCALE])


__all__ = [
    "LOCALE_PACKS",
    "LocalePack",
    "LocaleRegistry",
    "detect_locale",
    "detect_locale_from_story",
    "LOCALE_ALIASES",
    "get_locale_pack",
    "DEFAULT_LOCALE",
]
