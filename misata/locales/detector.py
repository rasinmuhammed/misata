"""
Locale detection from plain-English story text.

Looks for country names, city names, currency symbols, language indicators,
and cultural keywords to infer the most likely locale.

Returns a BCP-47 locale code string (e.g. "de_DE") or None if uncertain.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


# ── Keyword → locale mapping ──────────────────────────────────────────────────
# Each entry: (locale_code, weight, [keywords])
# Higher weight = stronger signal.  Exact matches beat substring matches.

_LOCALE_SIGNALS: List[Tuple[str, int, List[str]]] = [
    # ── United States ─────────────────────────────────────────────────────────
    ("en_US", 3, [
        "united states", "usa", "u.s.a", "u.s.",
        "american company", "american startup", "american market",
        "silicon valley", "san francisco", "new york city",
        "social security number", "ssn", "us dollar",
    ]),
    ("en_US", 2, [
        "american", "california", "texas", "new york", "chicago",
        "seattle", "boston", "austin", "denver", "los angeles",
        "zip code", "us market", "usd",
    ]),

    # ── United Kingdom ────────────────────────────────────────────────────────
    ("en_GB", 3, [
        "united kingdom", "uk company", "uk startup", "uk market",
        "british company", "british pounds", "sterling", "hmrc",
        "national insurance", "ni number", "postcode",
    ]),
    ("en_GB", 2, [
        "british", "england", "scotland", "wales", "london",
        "manchester", "birmingham", "glasgow", "liverpool",
        "edinburgh", "leeds", "bristol", "sheffield",
        "gbp", "£", "vat registered",
    ]),

    # ── Germany ───────────────────────────────────────────────────────────────
    ("de_DE", 3, [
        "germany", "german company", "german startup", "german market",
        "bundesrepublik", "steuer-id", "mehrwertsteuer",
        "gmbh", "aktiengesellschaft",
    ]),
    ("de_DE", 2, [
        "german", "berlin", "münchen", "munich", "hamburg",
        "frankfurt", "köln", "cologne", "düsseldorf", "stuttgart",
        "deutsche", "bundesbank",
    ]),

    # ── France ────────────────────────────────────────────────────────────────
    ("fr_FR", 3, [
        "france", "french company", "french startup", "french market",
        "société", "sarl", "numéro de sécu", "tva",
    ]),
    ("fr_FR", 2, [
        "french", "paris", "lyon", "marseille", "toulouse",
        "bordeaux", "nantes", "strasbourg", "montpellier",
        "française", "bfm", "insee",
    ]),

    # ── Brazil ────────────────────────────────────────────────────────────────
    ("pt_BR", 3, [
        "brazil", "brasil", "brazilian company", "brazilian startup",
        "cpf", "cnpj", "reais", "real brasileiro", "r$",
        "são paulo", "rio de janeiro",
    ]),
    ("pt_BR", 2, [
        "brazilian", "sao paulo", "brasília", "brasilia",
        "belo horizonte", "fortaleza", "porto alegre", "recife",
        "brl", "banco do brasil", "nubank",
    ]),

    # ── Spain ─────────────────────────────────────────────────────────────────
    ("es_ES", 3, [
        "spain", "españa", "spanish company", "spanish startup",
        "spanish market", "dni", "nif", "iva español",
    ]),
    ("es_ES", 2, [
        "spanish", "madrid", "barcelona", "valencia", "sevilla",
        "bilbao", "zaragoza", "málaga", "alicante",
        "empresa española",
    ]),

    # ── India ─────────────────────────────────────────────────────────────────
    ("hi_IN", 3, [
        "india", "indian company", "indian startup", "indian market",
        "aadhaar", "aadhar", "pan card", "gst india",
        "indian rupee", "inr", "₹",
    ]),
    ("hi_IN", 2, [
        "indian", "mumbai", "delhi", "bangalore", "bengaluru",
        "hyderabad", "chennai", "kolkata", "pune", "ahmedabad",
        "jaipur", "noida", "gurugram", "gurgaon",
        "bse", "nse", "sebi", "rbi",
    ]),

    # ── Japan ─────────────────────────────────────────────────────────────────
    ("ja_JP", 3, [
        "japan", "japanese company", "japanese startup", "japanese market",
        "my number", "マイナンバー", "kabushiki kaisha", "株式会社",
        "japanese yen", "jpy",
    ]),
    ("ja_JP", 2, [
        "japanese", "tokyo", "osaka", "kyoto", "nagoya",
        "sapporo", "fukuoka", "hiroshima", "yokohama",
        "nikkei", "softbank", "sony", "toyota market",
        "yen", "¥",
    ]),

    # ── China ─────────────────────────────────────────────────────────────────
    ("zh_CN", 3, [
        "china", "chinese company", "chinese startup", "chinese market",
        "renminbi", "rmb", "cny", "居民身份证", "yuan",
    ]),
    ("zh_CN", 2, [
        "chinese", "beijing", "shanghai", "shenzhen", "guangzhou",
        "chengdu", "wuhan", "hangzhou", "nanjing", "tianjin",
        "alibaba", "tencent", "baidu",
    ]),

    # ── Saudi Arabia / UAE ────────────────────────────────────────────────────
    ("ar_SA", 3, [
        "saudi arabia", "saudi company", "saudi startup",
        "sar", "riyal", "iqama", "vision 2030",
    ]),
    ("ar_SA", 2, [
        "saudi", "riyadh", "jeddah", "mecca", "medina",
        "dammam", "khobar", "uae", "dubai", "abu dhabi",
        "arabic company", "middle east",
    ]),

    # ── South Korea ───────────────────────────────────────────────────────────
    ("ko_KR", 3, [
        "south korea", "korean company", "korean startup", "korean market",
        "주민등록번호", "krw", "korean won",
    ]),
    ("ko_KR", 2, [
        "korean", "seoul", "busan", "incheon", "daegu",
        "samsung", "kakao", "naver", "kakaobank",
    ]),

    # ── Netherlands ───────────────────────────────────────────────────────────
    ("nl_NL", 3, [
        "netherlands", "dutch company", "dutch startup",
        "bsn nummer", "bsn", "btw-nummer", "kvk",
    ]),
    ("nl_NL", 2, [
        "dutch", "amsterdam", "rotterdam", "the hague", "utrecht",
        "eindhoven", "tilburg", "groningen",
        "rabobank", "ing bank", "abn amro",
    ]),

    # ── Italy ─────────────────────────────────────────────────────────────────
    ("it_IT", 3, [
        "italy", "italian company", "italian startup",
        "codice fiscale", "partita iva", "iva italiana",
    ]),
    ("it_IT", 2, [
        "italian", "rome", "milan", "naples", "turin",
        "florence", "bologna", "venice", "genoa",
        "unicredit", "intesa sanpaolo",
    ]),

    # ── Poland ────────────────────────────────────────────────────────────────
    ("pl_PL", 3, [
        "poland", "polish company", "polish startup",
        "pesel", "nip", "krs", "pln", "złoty",
    ]),
    ("pl_PL", 2, [
        "polish", "warsaw", "kraków", "krakow", "wrocław", "wroclaw",
        "łódź", "lodz", "poznań", "poznan", "gdańsk", "gdansk",
        "pko bank", "pekao",
    ]),

    # ── Turkey ────────────────────────────────────────────────────────────────
    ("tr_TR", 3, [
        "turkey", "turkish company", "turkish startup",
        "tc kimlik", "türk lirası", "try",
    ]),
    ("tr_TR", 2, [
        "turkish", "istanbul", "ankara", "izmir", "bursa",
        "antalya", "ziraat", "iş bankası", "garanti",
    ]),
]

# Flat alias dict for O(1) lookup (populated below)
LOCALE_ALIASES: Dict[str, str] = {}

for _locale, _weight, _keywords in _LOCALE_SIGNALS:
    for _kw in _keywords:
        # Store the highest-weight locale per keyword
        existing = LOCALE_ALIASES.get(_kw)
        if existing is None:
            LOCALE_ALIASES[_kw] = _locale


def detect_locale_from_story(story: str) -> Optional[str]:
    """Detect the most likely locale from *story* text.

    Scoring: each keyword match adds its weight to a per-locale tally.
    Returns the locale with the highest score, or ``None`` if no signal
    reaches a minimum threshold of 2.

    Args:
        story: Plain-English description string.

    Returns:
        BCP-47 locale code string or ``None``.

    Examples::

        detect_locale_from_story("A German SaaS with 500 users in Berlin")
        # → "de_DE"

        detect_locale_from_story("Indian fintech startup with ₹ payments")
        # → "hi_IN"

        detect_locale_from_story("An ecommerce store with 10k orders")
        # → None  (no locale signal; caller defaults to en_US)
    """
    if not story:
        return None

    story_lower = story.lower()
    scores: Dict[str, int] = {}

    for locale, weight, keywords in _LOCALE_SIGNALS:
        for kw in keywords:
            if kw in story_lower:
                scores[locale] = scores.get(locale, 0) + weight

    if not scores:
        return None

    best_locale = max(scores, key=lambda l: scores[l])
    if scores[best_locale] < 2:
        return None

    return best_locale


def locale_from_currency_symbol(symbol: str) -> Optional[str]:
    """Map a currency symbol to the most common locale that uses it.

    Note: ``€`` maps to ``de_DE`` (most common euro-zone country in dev data),
    ``¥`` maps to ``ja_JP`` (Chinese yuan uses same symbol but different code).
    """
    _MAP = {
        "$": "en_US",
        "£": "en_GB",
        "€": "de_DE",
        "₹": "hi_IN",
        "R$": "pt_BR",
        "¥": "ja_JP",
        "¥ (cny)": "zh_CN",
        "₩": "ko_KR",
        "﷼": "ar_SA",
        "zł": "pl_PL",
        "₺": "tr_TR",
    }
    return _MAP.get(symbol)
