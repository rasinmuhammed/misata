"""Gulf Arabic person names for the GCC locale packs.

Faker has a native Arabic person provider for ``ar_SA`` only. ``ar_AE``,
``ar_BH``, ``ar_JO`` and ``ar_EG`` fall back to the English provider
silently, so before this module a Qatari, Emirati, Kuwaiti, Bahraini or
Omani customer table came back with names like "Gerald Holden" next to
correctly localised cities and IDs.

The pools below are written in Arabic script, matching what ``ar_SA``
already returns, and family names are chosen per country so an Omani
table does not carry Qatari tribal names. Ruling-family surnames are left
out on purpose: a synthetic customer should not read as a real royal.

Family names carry the definite article, as they are written and stored in
the region ("الكواري", not "كواري").
"""

from __future__ import annotations

from typing import Dict, List, Tuple

_MALE: List[str] = [
    "محمد", "أحمد", "عبدالله", "خالد", "سالم", "سعود", "فهد", "ناصر", "راشد",
    "حمد", "علي", "يوسف", "إبراهيم", "عبدالرحمن", "سلطان", "مبارك", "جاسم",
    "عيسى", "ماجد", "طلال", "بدر", "فيصل", "سيف", "زايد", "حمدان", "سعيد",
    "عمر", "هلال", "منصور", "حسن", "حسين", "عبدالعزيز", "تركي", "مشعل",
    "نواف", "بندر", "عادل", "وليد", "طارق", "ماهر", "عبدالرزاق", "يعقوب",
    "جابر", "صقر", "عثمان", "مطر", "حميد", "ثامر",
]

_FEMALE: List[str] = [
    "فاطمة", "مريم", "عائشة", "نورة", "موزة", "شيخة", "سارة", "هند", "لولوة",
    "حصة", "خديجة", "أمل", "ريم", "دانة", "لطيفة", "منى", "سميرة", "نوف",
    "مها", "عالية", "جواهر", "شما", "ميثاء", "روضة", "حنان", "سلمى", "زينب",
    "رحمة", "آمنة", "بدرية", "نجلاء", "هيا", "العنود", "غالية", "أسماء",
    "خولة", "ليلى", "وضحى", "سعاد", "إيمان",
]

_FAMILY: Dict[str, List[str]] = {
    "ar_QA": [
        "الكواري", "النعيمي", "السليطي", "المري", "الهاجري", "المهندي",
        "العمادي", "الكعبي", "الدوسري", "المناعي", "المسند", "الخليفي",
        "البوعينين", "السادة", "الأنصاري", "العطية", "الجابر", "الدرهم",
    ],
    "ar_AE": [
        "الفلاسي", "السويدي", "المزروعي", "الشامسي", "الكتبي", "الظاهري",
        "المنصوري", "النعيمي", "الزعابي", "الحمادي", "البلوشي", "المهيري",
        "المرزوقي", "الرميثي", "الكعبي", "القبيسي", "الحبسي", "الشحي",
    ],
    "ar_KW": [
        "الغانم", "الخرافي", "المطيري", "العنزي", "الرشيدي", "العجمي",
        "الهاجري", "الدوسري", "الرومي", "البدر", "العتيبي", "الشمري",
        "الحربي", "الكندري", "الفضلي", "العوضي", "الصالح", "المطوع",
    ],
    "ar_BH": [
        "الزياني", "الفاضل", "المحمود", "الجلاهمة", "المطوع", "العلوي",
        "العالي", "الدوسري", "كانو", "المؤيد", "النعيمي", "البلوشي",
        "الأنصاري", "الشيراوي", "العرادي", "الجودر", "المناعي", "الحايكي",
    ],
    "ar_OM": [
        "البلوشي", "الحارثي", "الرواحي", "الكندي", "الحبسي", "الهنائي",
        "السيابي", "المسكري", "اللواتي", "الزدجالي", "الشكيلي", "الريامي",
        "المعمري", "الغافري", "العبري", "الفارسي", "البرواني", "الراشدي",
    ],
}

GULF_NAME_LOCALES: Tuple[str, ...] = tuple(_FAMILY)


def has_gulf_names(locale: str) -> bool:
    return locale in _FAMILY


def install_gulf_names(fake, locale: str) -> None:
    """Make ``fake`` return Gulf Arabic names for ``locale``.

    Registered as a Faker provider, so it overrides the English fallback for
    ``name``, ``first_name`` and ``last_name`` (and their gendered forms) and
    draws from the instance's own random source, which keeps a seeded run
    reproducible.
    """
    from faker.providers import BaseProvider

    family = _FAMILY[locale]
    male, female = _MALE, _FEMALE

    class GulfNameProvider(BaseProvider):
        def first_name_male(self) -> str:
            return self.random_element(male)

        def first_name_female(self) -> str:
            return self.random_element(female)

        def first_name(self) -> str:
            pool = male if self.generator.random.random() < 0.5 else female
            return self.random_element(pool)

        def last_name(self) -> str:
            return self.random_element(family)

        last_name_male = last_name
        last_name_female = last_name

        def name_male(self) -> str:
            return f"{self.first_name_male()} {self.last_name()}"

        def name_female(self) -> str:
            return f"{self.first_name_female()} {self.last_name()}"

        def name(self) -> str:
            return f"{self.first_name()} {self.last_name()}"

    fake.add_provider(GulfNameProvider)
