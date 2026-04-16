"""
LocaleRegistry — central access point for locale packs and Faker instances.

Caches Faker instances per locale so we don't recreate them on every row.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from misata.locales.packs import LOCALE_PACKS, LocalePack

if TYPE_CHECKING:
    pass


class LocaleRegistry:
    """Thread-safe cache of Faker instances keyed by locale code.

    Example::

        registry = LocaleRegistry()
        faker = registry.get_faker("de_DE")
        print(faker.name())          # German name
        print(faker.city())          # German city
        print(faker.phone_number())  # German phone format

        pack = registry.get_pack("de_DE")
        print(pack.currency_symbol)  # €
        print(pack.salary_median)    # 45000
    """

    _instance: Optional["LocaleRegistry"] = None

    def __init__(self) -> None:
        self._faker_cache: Dict[str, Any] = {}

    # ── Singleton ─────────────────────────────────────────────────────────────

    @classmethod
    def global_instance(cls) -> "LocaleRegistry":
        """Return a process-level singleton registry."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ── Faker ─────────────────────────────────────────────────────────────────

    def get_faker(self, locale: str = "en_US") -> Any:
        """Return a ``Faker`` instance for *locale*, creating it if needed.

        Falls back to ``en_US`` if the locale is not in the pack registry or
        if ``faker`` is not installed.
        """
        if locale in self._faker_cache:
            return self._faker_cache[locale]

        pack = LOCALE_PACKS.get(locale, LOCALE_PACKS.get("en_US"))
        faker_locale = pack.faker_locale if pack else locale

        try:
            from faker import Faker
            f = Faker(faker_locale)
            # Seed is set externally by the simulator — don't seed here
        except Exception:
            # faker not installed or locale not supported — use plain en_US
            try:
                from faker import Faker
                f = Faker("en_US")
            except Exception:
                f = None

        self._faker_cache[locale] = f
        return f

    # ── Pack ──────────────────────────────────────────────────────────────────

    def get_pack(self, locale: str) -> LocalePack:
        """Return the :class:`LocalePack` for *locale*, falling back to en_US."""
        return LOCALE_PACKS.get(locale, LOCALE_PACKS["en_US"])

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def supported_locales() -> list:
        """Return sorted list of all supported locale codes."""
        return sorted(LOCALE_PACKS.keys())
