"""
Realism rules for post-generation data adjustment.

These rules enforce cross-column mathematical and logical consistency
that the column-level generator cannot express. This is what separates
a realism engine from a random Faker.

Rules are applied conservatively — only when relevant columns exist.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

import numpy as np
import pandas as pd

from misata.domain_capsule import DomainCapsule
from misata.people import PersonSampler, lookup_gender, lookup_surname_culture
from misata.vocab_seeds import (
    CITIES_BY_COUNTRY,
    FIRST_NAMES,
    JOB_TITLES as _JOB_TITLES_BY_DOMAIN,
    LAST_NAMES,
    PRODUCT_BY_CATEGORY,
    STATES_BY_COUNTRY,
)


INACTIVE_STATUSES = {"inactive", "cancelled", "canceled", "ended", "expired", "churned"}
ACTIVE_STATUSES = {"active", "trialing", "trial", "enabled"}
DELIVERED_STATUSES = {"delivered", "completed", "fulfilled"}

# Geography — now sourced from the rich seed pools
COUNTRY_STATES = STATES_BY_COUNTRY
COUNTRY_CITIES = CITIES_BY_COUNTRY

COMPANY_PREFIXES = [
    "North", "Blue", "Peak", "Cedar", "Summit", "Atlas", "Bright", "Modern",
    "Vertex", "True", "Prime", "Nova", "Apex", "Ever", "Silver", "Quantum",
]
COMPANY_ROOTS = [
    "Labs", "Systems", "Works", "Health", "Retail", "Logic", "Cloud", "Supply",
    "Dynamics", "Analytics", "Commerce", "Bio", "Capital", "Foods", "Networks", "Studio",
]
COMPANY_SUFFIXES = ["Inc", "Group", "Co", "Partners", "Holdings", "Solutions", "Collective"]

JOB_TITLES = _JOB_TITLES_BY_DOMAIN["generic"]

COUNTRIES = list(CITIES_BY_COUNTRY.keys())

# Table-name substrings that make a bare "name" column a *person* name. Anything
# else (plans, statuses, types, categories) is a lookup/dimension table whose
# labels should come from the schema's inline_data, not a person generator.
_PERSON_TABLE_HINTS = (
    "user", "customer", "person", "people", "employee", "member", "contact",
    "author", "owner", "student", "patient", "doctor", "nurse", "driver",
    "rider", "agent", "seller", "buyer", "applicant", "client", "subscriber",
    "guest", "staff", "attendee", "participant", "passenger", "tenant", "donor",
    "player", "instructor", "teacher", "manager", "candidate", "lead",
)

# Generic, domain-neutral labels for a lookup table that arrived without
# inline_data — far better than person names or lorem sentences for a 3-20 row
# dimension table (plan tiers, statuses, types).
CATEGORY_LABELS = [
    "Standard", "Basic", "Premium", "Pro", "Enterprise", "Starter", "Plus",
    "Lite", "Advanced", "Core", "Team", "Business", "Free", "Custom", "Trial",
    "Active", "Inactive", "Pending", "Default", "Primary", "Secondary",
    "General", "Essential", "Professional", "Ultimate", "Growth", "Scale",
]

# Product name pools — now sourced from the rich seed pools
PRODUCT_NAME_POOLS = PRODUCT_BY_CATEGORY

PRODUCT_DESCRIPTION_TEMPLATES = [
    "Designed for everyday use with reliable performance and clean design.",
    "Built for teams that want quality, durability, and fast setup.",
    "A customer favorite for comfort, performance, and long-term value.",
    "Combines premium materials with practical features for daily use.",
]


class RealisticTextGenerator:
    """Catalog-backed text generation for semantic text columns."""

    def __init__(
        self,
        rng: Optional[np.random.Generator] = None,
        capsule: Optional[DomainCapsule] = None,
        locale: Optional[str] = None,
    ):
        self.rng = rng or np.random.default_rng(42)
        self.capsule = capsule
        self.locale = locale or "en_US"
        self._faker = None  # lazy
        # Per-(table, size) joint person frames so first_name, last_name and
        # gender for the same table come from ONE draw of (culture, gender,
        # first, last) — never independent samples that produce "Pablo, Female"
        # or "Wei Gonzalez".
        self._person_frames: dict = {}
        from misata.microtext import MicrotextGenerator
        self.microtext = MicrotextGenerator(self.rng)

    def _get_faker(self):
        if self._faker is None:
            try:
                from misata.locales.registry import LocaleRegistry
                self._faker = LocaleRegistry.global_instance().get_faker(self.locale)
            except Exception:
                try:
                    from faker import Faker
                    self._faker = Faker(self.locale)
                except Exception:
                    self._faker = None
        return self._faker

    def generate(
        self,
        column_name: str,
        table_name: str,
        size: int,
        semantic_type: Optional[str] = None,
        table_data: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        semantic = semantic_type or self._infer_semantic(column_name, table_name)

        # When a non-default locale is active, prefer Faker for person/address data
        # so names, cities, and phones match the target locale.
        # Exception: if the domain capsule already has vocabulary loaded for this
        # semantic type (e.g. from a Kaggle asset store), the capsule takes priority.
        def _has_non_fallback_capsule_vocab(key: str) -> bool:
            if not self.capsule or not self.capsule.vocabularies.get(key):
                return False
            provenances = self.capsule.provenance.get(key, [])
            return any(
                getattr(provenance, "source_name", "") != "misata-defaults"
                for provenance in provenances
            )

        _has_capsule_vocab = _has_non_fallback_capsule_vocab
        faker = self._get_faker() if self.locale != "en_US" else None

        if semantic == "first_name":
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.first_name() for _ in range(size)])
            if _has_capsule_vocab("first_name"):
                return self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
            return self._person_frame(table_name, size)["first"]
        if semantic == "last_name":
            if faker and not _has_capsule_vocab("last_name"):
                return np.array([faker.last_name() for _ in range(size)])
            if _has_capsule_vocab("last_name"):
                return self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
            return self._person_frame(table_name, size)["last"]
        if semantic == "person_name":
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.name() for _ in range(size)])
            if _has_capsule_vocab("first_name"):
                first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
                last = self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
                return np.array([f"{f} {l}" for f, l in zip(first, last)])
            return self._person_frame(table_name, size)["full"]
        if semantic == "email":
            # Use names already generated in this row when available
            _PROVIDERS = ["gmail.com", "outlook.com", "yahoo.com", "icloud.com", "protonmail.com", "hotmail.com"]
            _PWEIGHTS  = [0.42, 0.20, 0.14, 0.10, 0.08, 0.06]
            if table_data is not None and "first_name" in table_data.columns:
                first = table_data["first_name"].astype(str).values[:size]
                last  = table_data["last_name"].astype(str).values[:size] if "last_name" in table_data.columns else np.array([""] * size)
            elif faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.email() for _ in range(size)])
            elif not _has_capsule_vocab("first_name"):
                frame = self._person_frame(table_name, size)
                first, last = frame["first"], frame["last"]
            else:
                first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
                last  = self.rng.choice(self._vocabulary("last_name",  LAST_NAMES),  size=size)
            separators = self.rng.choice([".", "_", ""], size=size, p=[0.50, 0.20, 0.30])
            domains    = self.rng.choice(_PROVIDERS, size=size, p=_PWEIGHTS)
            patterns   = self.rng.integers(0, 4, size=size)
            result = []
            for fn, ln, sep, dom, pat in zip(first, last, separators, domains, patterns):
                f = re.sub(r"[^a-z]", "", fn.lower())
                l = re.sub(r"[^a-z]", "", ln.lower())
                if pat == 0:
                    local = f"{f}{sep}{l}" if l else f
                elif pat == 1:
                    local = f"{f[0]}{l}" if l else f
                elif pat == 2:
                    local = f"{f}{self.rng.integers(1, 999)}"
                else:
                    local = f"{f}{sep}{l[:3]}" if l else f
                result.append(f"{local or f or 'user'}@{dom}")
            return np.array(result)
        if semantic == "company_name":
            if faker:
                try:
                    from misata.locales.registry import LocaleRegistry
                    pack = LocaleRegistry.global_instance().get_pack(self.locale)
                    suffix = pack.company_suffixes
                    return np.array([f"{faker.company().split()[0]} {np.random.choice(suffix)}" for _ in range(size)])
                except Exception:
                    return np.array([faker.company() for _ in range(size)])
            company_names = self._vocabulary("company_name", [])
            if company_names:
                return self.rng.choice(company_names, size=size)
            return np.array(
                [
                    f"{self.rng.choice(COMPANY_PREFIXES)} {self.rng.choice(COMPANY_ROOTS)} {self.rng.choice(COMPANY_SUFFIXES)}"
                    for _ in range(size)
                ]
            )
        if semantic == "job_title":
            if faker:
                try:
                    return np.array([faker.job() for _ in range(size)])
                except Exception:
                    pass
            return self.rng.choice(self._vocabulary("job_title", JOB_TITLES), size=size)
        if semantic == "country":
            if self.locale != "en_US":
                try:
                    from misata.locales.registry import LocaleRegistry
                    pack = LocaleRegistry.global_instance().get_pack(self.locale)
                    return np.array([pack.country_name] * size)
                except Exception:
                    pass
            return self.rng.choice(self._vocabulary("country", COUNTRIES), size=size)
        if semantic == "state":
            if faker:
                try:
                    return np.array([faker.city() for _ in range(size)])  # state/prefecture via city for non-US
                except Exception:
                    pass
            countries = self._series_from_table(table_data, "country", size)
            states = self._vocabulary("state", [])
            if states:
                return self.rng.choice(states, size=size)
            return np.array([
                self.rng.choice(COUNTRY_STATES.get(country, COUNTRY_STATES["United States"]))
                for country in countries
            ])
        if semantic == "city":
            # Use locale pack top_cities list when available (real, population-ranked)
            try:
                from misata.locales.registry import LocaleRegistry
                pack = LocaleRegistry.global_instance().get_pack(self.locale)
                if pack.top_cities:
                    return self.rng.choice(pack.top_cities, size=size)
            except Exception:
                pass
            if faker:
                try:
                    return np.array([faker.city() for _ in range(size)])
                except Exception:
                    pass
            countries = self._series_from_table(table_data, "country", size)
            cities = self._vocabulary("city", [])
            if cities:
                return self.rng.choice(cities, size=size)
            return np.array([
                self.rng.choice(COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"]))
                for country in countries
            ])
        if semantic == "username":
            frame = self._person_frame(table_name, size)
            first, last = frame["first"], frame["last"]
            return np.array([
                f"{re.sub(r'[^a-z]', '', f.lower())}{re.sub(r'[^a-z]', '', l.lower())}{int(self.rng.integers(1, 999)):03d}"
                for f, l in zip(first, last)
            ])
        if semantic == "address":
            numbers = self.rng.integers(10, 9999, size=size)
            streets = self.rng.choice(["Main", "Oak", "Maple", "Cedar", "Sunset", "Lake"], size=size)
            suffixes = self.rng.choice(["St", "Ave", "Blvd", "Ln", "Rd"], size=size)
            return np.array([f"{n} {street} {suffix}" for n, street, suffix in zip(numbers, streets, suffixes)])
        if semantic == "phone_number":
            return self._generate_phone_number(size=size)
        if semantic == "national_id":
            return self._generate_national_id(size=size)
        if semantic == "url":
            slugs = self._slugify(self.generate(column_name, table_name, size, "company_name"))
            return np.array([f"https://www.{slug}.com" for slug in slugs])
        if semantic == "slug_source":
            words = self.rng.choice(["modern", "prime", "atlas", "core", "blue", "summit"], size=(size, 2))
            return np.array([f"{left}-{right}" for left, right in words])
        if semantic == "category_label":
            return self.rng.choice(self._vocabulary("category_label", CATEGORY_LABELS), size=size)
        if semantic in {"product_name", "product_description"}:
            return self._generate_product_text(size=size, semantic=semantic, table_data=table_data)
        if semantic == "bio":
            return self._generate_bio(size=size)
        if semantic == "caption":
            return self._generate_caption(size=size, table_data=table_data)
        if semantic == "comment_body":
            return self._generate_comment_body(size=size)
        if semantic == "restaurant_name":
            return self._generate_restaurant_name(size=size)
        if semantic == "menu_item":
            return self._generate_menu_item(size=size, table_data=table_data)
        if semantic == "research_project_name":
            return self._generate_research_project_name(size=size)
        if semantic == "latitude":
            return self._generate_latitude(size=size)
        if semantic == "longitude":
            return self._generate_longitude(size=size)
        if semantic == "postal_code":
            return self._generate_postal_code(size=size)
        if semantic == "short_review_title":
            return self._generate_short_review_title(size=size, table_data=table_data)
        if semantic == "review":
            return self._generate_review(size=size, table_data=table_data)
        if semantic == "support_ticket":
            return self._generate_support_ticket(size=size)
        if semantic == "email_body":
            return self._generate_email_body(size=size)

        return np.array([
            self.rng.choice(self._vocabulary("product_description", PRODUCT_DESCRIPTION_TEMPLATES))
            for _ in range(size)
        ])

    def _infer_semantic(self, column_name: str, table_name: str) -> str:
        name = column_name.lower()
        table = table_name.lower()
        if name == "first_name":
            return "first_name"
        if name == "last_name":
            return "last_name"
        if "email" in name:
            return "email"
        if "company" in name or "organization" in name:
            return "company_name"
        if "username" in name:
            return "username"
        if "job" in name or "role" in name or "title" in name:
            return "job_title"
        if "country" in name:
            return "country"
        if "state" in name or "province" in name or "region" in name:
            return "state"
        if "city" in name:
            return "city"
        if name in ("lat", "latitude"):
            return "latitude"
        if name in ("lon", "lng", "longitude"):
            return "longitude"
        if name in ("zip", "zip_code", "postal", "postal_code", "postcode"):
            return "postal_code"
        if "phone" in name or "mobile" in name or "tel" in name:
            return "phone_number"
        if name in ("domain", "website", "site", "homepage") or name.endswith("_domain") or name.endswith("_url"):
            return "url"
        if name in ("national_id", "ssn", "cpf", "aadhaar", "nid", "tax_id") or "national_id" in name:
            return "national_id"
        if name in ("review", "review_text", "review_body"):
            return "review"
        if name in ("ticket_body", "issue_body", "support_ticket", "description") and (
            "ticket" in table or "issue" in table or "support" in table
        ):
            return "support_ticket"
        if name in ("email_body", "message_body", "message", "body") and (
            "email" in table or "message" in table or "inbox" in table
        ):
            return "email_body"
        if "restaurant" in table and name == "name":
            return "restaurant_name"
        if "restaurant" in table or ("item" in table and "order" in table):
            if name in ("item_name", "dish", "menu_item"):
                return "menu_item"
        if "research" in table or "project" in table:
            if name in ("project_name", "study_name", "trial_name"):
                return "research_project_name"
        if "comment" in table and name == "body":
            return "comment_body"
        if "product" in table or "item" in table or "listing" in table:
            return "product_name"
        if name in ("name", "full_name", "display_name"):
            # Only a *person* table's bare "name" is a person. A lookup/dimension
            # table (plans, statuses, types, categories) should carry its real
            # labels via inline_data; if it doesn't, a person name is the worst
            # possible guess, so fall through to a neutral short label instead.
            if any(p in table for p in _PERSON_TABLE_HINTS):
                return "person_name"
            return "category_label"
        if name.endswith("_name"):
            # batch_name, block_name, tank_name, event_name, plan_name, ... —
            # person/company/product *_name are already handled above, so what
            # reaches here is an entity label, not a lorem sentence.
            if any(p in table for p in _PERSON_TABLE_HINTS):
                return "person_name"
            return "category_label"
        # Short categorical-label columns: a free-text status/type/tier should be
        # a label, not a lorem sentence (these usually arrive as enums/inline_data;
        # this is the fallback when they don't).
        if name in (
            "status", "type", "category", "tier", "level", "kind", "stage",
            "label", "grade", "class", "mode", "priority", "severity", "plan",
        ):
            return "category_label"
        if name in ("bio", "about"):
            return "bio"
        if name == "caption":
            return "caption"
        if name in ("body", "description", "summary"):
            return "product_description"
        return "description"

    def _generate_caption(self, *, size: int, table_data: Optional[pd.DataFrame] = None) -> np.ndarray:  # noqa: ARG002
        _TEMPLATES = [
            "loving every moment of this {adj} journey ✨",
            "when the {noun} hits just right 🙌",
            "grateful for days like this 🌟",
            "this {adj} view never gets old 📸",
            "making memories that matter 💫",
            "small moments, big vibes ☀️",
            "just another {adj} day doing what I love",
            "the {noun} life chose me 🔥",
            "chasing {noun}s and good energy ✌️",
            "no filter needed when the {noun} is this good 🌿",
        ]
        _ADJ = ["beautiful", "wild", "golden", "peaceful", "chaotic", "amazing", "cozy", "electric"]
        _NOUN = ["creative", "adventure", "coffee", "sunset", "hustle", "moment", "vibe", "grind"]
        _TAGS = [
            "#lifestyle", "#instagood", "#photooftheday", "#love", "#happy",
            "#travel", "#nature", "#food", "#art", "#motivation",
            "#explore", "#vibes", "#authentic", "#grateful", "#daily",
        ]
        results = []
        for _ in range(size):
            tmpl = self.rng.choice(_TEMPLATES)
            text = tmpl.format(
                adj=self.rng.choice(_ADJ),
                noun=self.rng.choice(_NOUN),
            )
            n_tags = int(self.rng.integers(2, 6))
            tags = " ".join(self.rng.choice(_TAGS, size=n_tags, replace=False))
            results.append(f"{text} {tags}")
        return np.array(results)

    def _generate_bio(self, *, size: int) -> np.ndarray:
        _ROLES = ["developer", "designer", "founder", "marketer", "photographer",
                  "writer", "artist", "engineer", "entrepreneur", "creator",
                  "traveller", "chef", "coach", "consultant", "student"]
        _VIBES = ["sharing what I love", "living my best life", "making things happen",
                  "building in public", "exploring the world", "chasing ideas",
                  "creating every day", "telling stories", "obsessed with details",
                  "always learning", "turning coffee into code", "dreaming big",
                  "on a mission", "figuring it all out", "here for the journey"]
        _EXTRAS = ["", " ✌️", " 🌍", " 🚀", " 💡", " 📸", " 🎨", " ☕", "", ""]
        roles = self.rng.choice(_ROLES, size=size)
        vibes = self.rng.choice(_VIBES, size=size)
        extras = self.rng.choice(_EXTRAS, size=size)
        return np.array([f"{r.capitalize()} | {v}{e}" for r, v, e in zip(roles, vibes, extras)])

    def _generate_latitude(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import CITY_GEODATA
        cities = self.rng.choice(len(CITY_GEODATA), size=size)
        lats = np.array([CITY_GEODATA[i][1] for i in cities])
        # Small Gaussian jitter within ~50 km
        lats += self.rng.normal(0, 0.25, size=size)
        return np.round(lats, 6)

    def _generate_longitude(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import CITY_GEODATA
        cities = self.rng.choice(len(CITY_GEODATA), size=size)
        lngs = np.array([CITY_GEODATA[i][2] for i in cities])
        lngs += self.rng.normal(0, 0.35, size=size)
        return np.round(lngs, 6)

    def _generate_postal_code(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import CITY_GEODATA
        cities = self.rng.choice(len(CITY_GEODATA), size=size)
        codes = []
        for i in cities:
            prefix = CITY_GEODATA[i][3]
            suffix = "".join(str(self.rng.integers(0, 10)) for _ in range(5 - len(prefix)))
            codes.append(f"{prefix}{suffix}")
        return np.array(codes)

    def _generate_short_review_title(self, *, size: int, table_data: Optional[pd.DataFrame] = None) -> np.ndarray:
        return self.microtext.review_titles(size, ratings=self._ratings_from(table_data, size))

    def _ratings_from(self, table_data: Optional[pd.DataFrame], size: int):
        """The row's own rating column, if one has been generated already."""
        if table_data is None:
            return None
        for col in ("rating", "stars", "score", "rating_given"):
            if col in table_data.columns:
                return table_data[col].values[:size]
        return None

    def _generate_review(self, *, size: int, table_data: Optional[pd.DataFrame] = None) -> np.ndarray:
        # Sentiment is conditioned on the row's rating: a 1-star review reads
        # angry, a 5-star review reads delighted. Without a rating column the
        # grammar falls back to the J-shaped marginal real review sites show.
        return self.microtext.reviews(size, ratings=self._ratings_from(table_data, size))

    def _generate_support_ticket(self, *, size: int) -> np.ndarray:
        _ISSUES = [
            "I'm unable to log into my account after the recent update.",
            "The payment keeps failing at checkout — tried three different cards.",
            "My order shows as delivered but I haven't received anything.",
            "The app crashes every time I try to open the settings page.",
            "I was charged twice for the same transaction.",
            "My subscription was cancelled but I'm still being billed.",
            "I can't upload files larger than 5 MB — getting an error.",
            "The export feature produces an empty CSV file.",
            "Two-factor authentication isn't sending the verification code.",
            "The dashboard isn't loading any data since this morning.",
            "I need to update my billing address but the form won't save.",
            "My API key stopped working after I regenerated it.",
            "The integration with Slack stopped sending notifications.",
            "I deleted data by mistake — is there a way to recover it?",
            "The mobile app is showing stale data that won't refresh.",
        ]
        _CONTEXT = [
            "This started happening around 2 days ago.",
            "I've tried clearing cache and it didn't help.",
            "This is blocking my team from completing their work.",
            "I've already tried restarting the app with no success.",
            "It works fine on desktop but not on mobile.",
            "I'm on the Pro plan, account ID in my profile.",
            "Please escalate — this is urgent.",
            "",
            "",
            "",
        ]
        issues  = self.rng.choice(_ISSUES,   size=size)
        context = self.rng.choice(_CONTEXT,  size=size)
        return np.array([
            f"{i} {c}".strip() for i, c in zip(issues, context)
        ])

    def _generate_email_body(self, *, size: int) -> np.ndarray:
        _GREETINGS = ["Hi", "Hello", "Hey", "Dear team", "Hi there", "Good morning"]
        _BODIES = [
            "I wanted to follow up on our conversation from last week. Could you share an update?",
            "Please find the requested report attached. Let me know if you have any questions.",
            "Just a quick reminder that the deadline is approaching. Please confirm your status.",
            "Thank you for your response. I've reviewed the proposal and have a few comments.",
            "I'd like to schedule a call to discuss the project scope. Are you free this week?",
            "Following up on the invoice sent last month — could you confirm receipt?",
            "I've noticed a discrepancy in the report. Can we sync to go over the numbers?",
            "Happy to connect whenever you're available. Looking forward to working together.",
            "The documents have been reviewed and approved. You're good to proceed.",
            "We're running behind schedule. I'll send a revised timeline by end of day.",
        ]
        _CLOSINGS = [
            "Best regards,", "Thanks,", "Cheers,", "Kind regards,",
            "Looking forward to hearing from you,", "Best,", "Warm regards,",
        ]
        greetings = self.rng.choice(_GREETINGS, size=size)
        bodies    = self.rng.choice(_BODIES,    size=size)
        closings  = self.rng.choice(_CLOSINGS,  size=size)
        return np.array([
            f"{g},\n\n{b}\n\n{c}" for g, b, c in zip(greetings, bodies, closings)
        ])

    def _generate_restaurant_name(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import RESTAURANT_NAMES
        pool = self._vocabulary("restaurant_name", RESTAURANT_NAMES)
        return np.array([self.rng.choice(pool) for _ in range(size)])

    def _generate_menu_item(self, *, size: int, table_data: Optional[pd.DataFrame] = None) -> np.ndarray:
        from misata.vocab_seeds import MENU_ITEMS_BY_CATEGORY
        categories = self._series_from_table(table_data, "category", size)
        result = []
        fallback = MENU_ITEMS_BY_CATEGORY["main"]
        for cat in categories:
            pool = MENU_ITEMS_BY_CATEGORY.get(str(cat).lower(), fallback)
            pool = self._vocabulary(f"menu_item_{cat}", pool)
            result.append(self.rng.choice(pool))
        return np.array(result)

    def _generate_comment_body(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import COMMENT_BODIES
        pool = self._vocabulary("comment_body", [])
        if pool:  # capsule/asset-store vocabulary takes priority
            return np.array([self.rng.choice(pool) for _ in range(size)])
        # Grammar comments compose combinatorially; blend in the curated pool
        # for extra surface variety.
        generated = self.microtext.comments(size)
        from_pool = self.rng.random(size) < 0.3
        if from_pool.any():
            generated[from_pool] = self.rng.choice(COMMENT_BODIES, size=int(from_pool.sum()))
        return generated

    def _generate_research_project_name(self, *, size: int) -> np.ndarray:
        from misata.vocab_seeds import RESEARCH_PROJECT_NAMES
        pool = self._vocabulary("research_project_name", RESEARCH_PROJECT_NAMES)
        return np.array([self.rng.choice(pool) for _ in range(size)])

    def _generate_phone_number(self, *, size: int) -> np.ndarray:
        try:
            from misata.locales.registry import LocaleRegistry
            pack = LocaleRegistry.global_instance().get_pack(self.locale)
            prefix = pack.phone_prefix  # e.g. "+1", "+44", "+49"
        except Exception:
            prefix = "+1"

        results = []
        cc = prefix.lstrip("+")

        for _ in range(size):
            if cc == "1":  # North America: +1 (NXX) NXX-XXXX
                area = self.rng.integers(200, 999)
                exch = self.rng.integers(200, 999)
                line = self.rng.integers(1000, 9999)
                results.append(f"+1 ({area}) {exch}-{line}")
            elif cc == "44":  # UK: +44 7XXX XXXXXX (mobile) or +44 XX XXXX XXXX
                if self.rng.random() < 0.6:
                    mid = self.rng.integers(7000, 7999)
                    tail = self.rng.integers(100000, 999999)
                    results.append(f"+44 {mid} {tail}")
                else:
                    area = self.rng.integers(20, 99)
                    mid = self.rng.integers(1000, 9999)
                    tail = self.rng.integers(1000, 9999)
                    results.append(f"+44 {area} {mid} {tail}")
            elif cc == "91":  # India: +91 XXXXX XXXXX
                first = self.rng.integers(70000, 99999)
                last = self.rng.integers(10000, 99999)
                results.append(f"+91 {first} {last}")
            elif cc in ("49", "33", "34", "39", "31", "48", "90"):  # Europe: +CC XXX XXXXXXX
                area = self.rng.integers(100, 999)
                body = self.rng.integers(1000000, 9999999)
                results.append(f"{prefix} {area} {body}")
            elif cc in ("81", "82", "86"):  # East Asia: +CC XX XXXX XXXX
                area = self.rng.integers(10, 99)
                mid = self.rng.integers(1000, 9999)
                tail = self.rng.integers(1000, 9999)
                results.append(f"{prefix} {area} {mid} {tail}")
            else:  # Generic international: +CC XXXXXXXXXX
                body = self.rng.integers(1000000000, 9999999999)
                results.append(f"{prefix} {body}")

        return np.array(results)

    def _generate_national_id(self, *, size: int) -> np.ndarray:
        try:
            from misata.locales.registry import LocaleRegistry
            pattern = LocaleRegistry.global_instance().get_pack(self.locale).national_id_pattern
        except Exception:
            pattern = r"\d{9}"
        return np.array([self._expand_pattern(pattern) for _ in range(size)])

    def _expand_pattern(self, pattern: str) -> str:
        """Expand the limited locale-pack regex patterns into deterministic strings."""
        output = ""
        i = 0
        while i < len(pattern):
            token = pattern[i]
            if pattern.startswith(r"\d", i):
                char_type = "digit"
                i += 2
            elif token == "[":
                end = pattern.find("]", i)
                body = pattern[i + 1:end] if end != -1 else "A-Z"
                if "A-Z" in body:
                    char_type = "letter"
                elif "a-z" in body:
                    char_type = "lower"
                else:
                    char_type = "literal"
                i = end + 1 if end != -1 else i + 1
            elif token == "\\" and i + 1 < len(pattern):
                output += pattern[i + 1]
                i += 2
                continue
            else:
                output += token
                i += 1
                continue

            repeat = 1
            if i < len(pattern) and pattern[i] == "{":
                end = pattern.find("}", i)
                if end != -1:
                    try:
                        repeat = int(pattern[i + 1:end])
                    except ValueError:
                        repeat = 1
                    i = end + 1

            if char_type == "digit":
                output += "".join(str(int(self.rng.integers(0, 10))) for _ in range(repeat))
            elif char_type == "letter":
                output += "".join(chr(int(self.rng.integers(65, 91))) for _ in range(repeat))
            elif char_type == "lower":
                output += "".join(chr(int(self.rng.integers(97, 123))) for _ in range(repeat))

        return output

    def _generate_product_text(
        self,
        *,
        size: int,
        semantic: str,
        table_data: Optional[pd.DataFrame],
    ) -> np.ndarray:
        categories = self._series_from_table(table_data, "category", size)
        values = []
        for category in categories:
            normalized = str(category).lower()
            key = next((pool for pool in PRODUCT_NAME_POOLS if pool in normalized), None)
            key = key or "electronics"
            if semantic == "product_name":
                product_names = self._vocabulary("product_name", PRODUCT_NAME_POOLS[key])
                values.append(self.rng.choice(product_names))
            else:
                product_descriptions = self._vocabulary("product_description", PRODUCT_DESCRIPTION_TEMPLATES)
                values.append(self.rng.choice(product_descriptions))
        return np.array(values)

    def _series_from_table(self, table_data: Optional[pd.DataFrame], column: str, size: int) -> np.ndarray:
        if table_data is not None and column in table_data.columns and len(table_data[column]) >= size:
            return table_data[column].astype(str).values[:size]
        return np.array(["United States"] * size)

    def _slugify(self, values: Iterable[str]) -> np.ndarray:
        slugs = []
        for value in values:
            slug = re.sub(r"[^a-z0-9\s-]", "", str(value).lower())
            slug = re.sub(r"\s+", "-", slug).strip("-")
            slugs.append(slug or "site")
        return np.array(slugs)

    def _person_frame(self, table_name: str, size: int) -> dict:
        """One joint (culture, gender, first, last) draw per table.

        Every person-ish column in the same table (first_name, last_name,
        full name, username, email fallback) reads from the same frame, so
        cross-column dependence is exact by construction.
        """
        key = (table_name, size)
        frame = self._person_frames.get(key)
        if frame is None:
            frame = PersonSampler(self.rng).sample(size)
            self._person_frames[key] = frame
        return frame

    def _vocabulary(self, name: str, fallback: Iterable[str]) -> list[str]:
        if self.capsule is not None:
            values = self.capsule.get_values(name, list(fallback))
            if values:
                return values
        return list(fallback)


class EntityCoherenceEngine:
    """High-confidence cross-column coherence rules."""

    def __init__(
        self,
        rng: Optional[np.random.Generator] = None,
        capsule: Optional[DomainCapsule] = None,
    ):
        self.rng = rng or np.random.default_rng(42)
        self.text_generator = RealisticTextGenerator(self.rng, capsule=capsule)

    def apply(
        self,
        df: pd.DataFrame,
        table_name: str,
        *,
        mode: str = "standard",
        protected_columns: Optional[set[str]] = None,
    ) -> pd.DataFrame:
        if df.empty or mode == "off":
            return df

        protected_columns = protected_columns or set()
        output = df.copy()
        columns = set(output.columns)

        self._fix_email_from_name(output, columns, protected_columns, mode)
        self._fix_username_from_name(output, columns, protected_columns, mode)
        self._fix_geography(output, columns, protected_columns, mode)
        self._fix_age_role(output, columns, protected_columns)
        self._fix_product_category(output, columns, protected_columns, mode, table_name.lower())

        return output

    def _fix_email_from_name(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "email" in protected or "email" not in columns:
            return

        if {"first_name", "last_name"}.issubset(columns):
            firsts = df["first_name"].astype(str)
            lasts = df["last_name"].astype(str)
        elif "name" in columns:
            parts = df["name"].astype(str).str.split()
            firsts = parts.apply(lambda values: values[0] if values else "user")
            lasts = parts.apply(lambda values: values[-1] if len(values) > 1 else "")
        else:
            return

        desired = np.array([
            f"{re.sub(r'[^a-z]', '', str(first).lower())}.{re.sub(r'[^a-z]', '', str(last).lower())}@gmail.com".replace("..", ".").replace(".@", "@")
            for first, last in zip(firsts, lasts)
        ])
        current = df["email"].astype(str)
        mismatch = []
        for email, first in zip(current, firsts.astype(str)):
            normalized_first = re.sub(r"[^a-z]", "", first.lower())[:3]
            normalized_email = str(email).lower()
            mismatch.append("@" not in normalized_email or (normalized_first and normalized_first not in normalized_email))
        mismatch_mask = np.array(mismatch, dtype=bool)
        if mode == "strict":
            mismatch_mask[:] = True
        df.loc[mismatch_mask, "email"] = desired[mismatch_mask]

    def _fix_username_from_name(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "username" in protected or "username" not in columns:
            return
        if {"first_name", "last_name"}.issubset(columns):
            firsts = df["first_name"].astype(str)
            lasts = df["last_name"].astype(str)
        elif "name" in columns:
            parts = df["name"].astype(str).str.split()
            firsts = parts.apply(lambda values: values[0] if values else "user")
            lasts = parts.apply(lambda values: values[-1] if len(values) > 1 else "")
        else:
            return

        desired = np.array([
            f"{re.sub(r'[^a-z]', '', str(first).lower())}{re.sub(r'[^a-z]', '', str(last).lower())}"
            for first, last in zip(firsts, lasts)
        ])
        current = df["username"].astype(str)
        mismatch = []
        for username, first, last in zip(current, firsts.astype(str), lasts.astype(str)):
            normalized_username = re.sub(r"[^a-z]", "", str(username).lower())
            normalized_first = re.sub(r"[^a-z]", "", str(first).lower())[:3]
            normalized_last = re.sub(r"[^a-z]", "", str(last).lower())[:3]
            mismatch.append(
                len(normalized_username) < 4
                or (normalized_first and normalized_first not in normalized_username)
                or (normalized_last and normalized_last not in normalized_username)
            )
        mismatch_mask = np.array(mismatch, dtype=bool)
        if mode == "strict":
            mismatch_mask[:] = True
        df.loc[mismatch_mask, "username"] = desired[mismatch_mask]

    def _fix_geography(self, df: pd.DataFrame, columns: set[str], protected: set[str], mode: str) -> None:
        if "country" not in columns:
            return
        countries = df["country"].astype(str)
        capsule_states = self.text_generator._vocabulary("state", [])
        capsule_cities = self.text_generator._vocabulary("city", [])

        if "state" in columns and "state" not in protected:
            if capsule_states:
                desired_states = np.array([self.rng.choice(capsule_states) for _ in countries])
            else:
                desired_states = np.array([
                    self.rng.choice(COUNTRY_STATES.get(country, COUNTRY_STATES["United States"]))
                    for country in countries
                ])
            current = df["state"].astype(str)
            if capsule_states:
                mismatch = ~current.isin(capsule_states).to_numpy()
            else:
                mismatch = np.array([
                    current.iloc[i] not in COUNTRY_STATES.get(country, COUNTRY_STATES["United States"])
                    for i, country in enumerate(countries)
                ])
            if mode == "strict":
                mismatch[:] = True
            df.loc[mismatch, "state"] = desired_states[mismatch]

        if "city" in columns and "city" not in protected:
            if capsule_cities:
                desired_cities = np.array([self.rng.choice(capsule_cities) for _ in countries])
            else:
                desired_cities = np.array([
                    self.rng.choice(COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"]))
                    for country in countries
                ])
            current = df["city"].astype(str)
            if capsule_cities:
                mismatch = ~current.isin(capsule_cities).to_numpy()
            else:
                mismatch = np.array([
                    current.iloc[i] not in COUNTRY_CITIES.get(country, COUNTRY_CITIES["United States"])
                    for i, country in enumerate(countries)
                ])
            if mode == "strict":
                mismatch[:] = True
            df.loc[mismatch, "city"] = desired_cities[mismatch]

    def _fix_age_role(self, df: pd.DataFrame, columns: set[str], protected: set[str]) -> None:
        if "age" in protected or "age" not in columns:
            return
        role_column = next((name for name in ["job_title", "title", "role", "position"] if name in columns), None)
        if role_column is None:
            return

        minimum_age = {
            "manager": 30, "director": 35, "vp": 38, "vice president": 38,
            "cto": 38, "ceo": 40, "chief": 40, "intern": 18, "senior": 28,
        }
        ages = pd.to_numeric(df["age"], errors="coerce").fillna(18).astype(int).values
        roles = df[role_column].astype(str).str.lower()
        for index, role in enumerate(roles):
            floor = 18
            for keyword, age_floor in minimum_age.items():
                if keyword in role:
                    floor = max(floor, age_floor)
            if ages[index] < floor:
                ages[index] = int(self.rng.integers(floor, min(65, floor + 10)))
        df["age"] = ages

    def _fix_product_category(
        self,
        df: pd.DataFrame,
        columns: set[str],
        protected: set[str],
        mode: str,
        table_name: str,
    ) -> None:
        if "name" in protected or "category" not in columns or "name" not in columns:
            return
        if "product" not in table_name and "item" not in table_name:
            return

        categories = df["category"].astype(str).str.lower()
        current_names = df["name"].astype(str)
        desired_names = []
        mismatches = []
        for category, current_name in zip(categories, current_names):
            key = next((pool for pool in PRODUCT_NAME_POOLS if pool in category), None)
            key = key or "electronics"
            desired_name = self.rng.choice(PRODUCT_NAME_POOLS[key])
            desired_names.append(desired_name)
            generic = any(token in current_name.lower() for token in ["lorem", "ipsum", "dolor", "product"])
            mismatches.append(generic or mode == "strict")
        desired_series = np.array(desired_names)
        mismatch_array = np.array(mismatches, dtype=bool)
        df.loc[mismatch_array, "name"] = desired_series[mismatch_array]


def apply_realism_rules(
    df: pd.DataFrame,
    table_name: str = "",
    rng: Optional[np.random.Generator] = None,
) -> pd.DataFrame:
    """
    Apply cross-column realism rules to a DataFrame.

    Order matters: simpler fixes first, computed columns last.
    Pass a seeded ``rng`` to guarantee reproducible fixups.
    """
    if df.empty:
        return df

    _rng = rng if rng is not None else np.random.default_rng(42)

    df = df.copy()
    columns = set(df.columns)

    # ── Temporal consistency ──
    _fix_created_updated(df, columns, _rng)
    _fix_start_end_dates(df, columns, _rng)
    _fix_created_delivered(df, columns, _rng)
    _fix_delivered_requires_status(df, columns)

    # ── Monetary consistency ──
    _fix_cost_less_than_price(df, columns, _rng)
    _fix_discount_cap(df, columns)
    _fix_line_total(df, columns)
    _fix_order_total(df, columns)
    _apply_plan_price_mapping(df, columns)

    # ── Identity consistency ──
    _fix_gender_name_coherence(df, columns, _rng)   # before email: email derives from the fixed name
    _fix_email_from_name(df, columns, _rng)
    _fix_slug_from_name(df, columns)
    _fix_category_from_product_name(df, columns, table_name)

    # ── Geographic consistency ──
    _fix_route_geo(df, columns, _rng)

    # ── Text/sentiment consistency ──
    _fix_review_sentiment(df, columns, _rng)

    # ── Status consistency ──
    _apply_status_end_date(df, columns, _rng)

    return df


# ─── TEXT / SENTIMENT RULES ──────────────────────────────────────────────────

_REVIEW_TEXT_COLS = ("review", "review_text", "review_body", "feedback_text")
_RATING_COLS = ("rating", "stars", "score", "rating_given")


def _fix_review_sentiment(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Make review text agree with the row's rating — regardless of the
    order columns were generated in.

    A five-star review that reads "disappointing" is both a realism tell and
    a conformance violation. Text is regenerated FROM the rating via the
    seeded grammar, making sentiment↔rating an invariant the Oracle layer
    can verify with a lexicon check.
    """
    rating_col = next((c for c in _RATING_COLS if c in columns), None)
    if rating_col is None:
        return

    from misata.microtext import MicrotextGenerator

    text_col = next((c for c in _REVIEW_TEXT_COLS if c in columns), None)
    # plain "title" is too generic to rewrite blindly; review_title is safe
    title_col = "review_title" if "review_title" in columns else None
    if text_col is None and title_col is None:
        return

    gen = MicrotextGenerator(rng)
    ratings = df[rating_col].values
    if text_col is not None:
        df[text_col] = gen.reviews(len(df), ratings=ratings)
    if title_col is not None:
        df[title_col] = gen.review_titles(len(df), ratings=ratings)


# ─── GEOGRAPHIC RULES ─────────────────────────────────────────────────────────

_ORIGIN_COLS = ("origin_city", "origin", "from_city", "source_city")
_DEST_COLS = ("destination_city", "destination", "to_city", "dest_city")
_DISTANCE_COLS = ("distance_km", "distance")
_TRAVEL_COLS = ("estimated_hours", "duration_hours", "travel_hours", "transit_hours")


def _fix_route_geo(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Make route distances and travel times agree with the named cities.

    Distance between two real cities is a fact, not a distribution:
    "Chicago → San Diego, 145 km" is an instant fake-data tell. For city
    pairs with known coordinates we set ``distance = haversine × road
    circuity`` and ``hours = distance / effective speed + handling`` —
    deterministic, so conformance is verifiable. Unknown cities are left
    untouched, and same-city routes get a different known destination first.
    """
    from misata.geo import (
        CITY_COORDS,
        EFFECTIVE_SPEED_KMH,
        HANDLING_OVERHEAD_H,
        ROAD_CIRCUITY,
        haversine_km,
    )

    origin_col = next((c for c in _ORIGIN_COLS if c in columns), None)
    dest_col = next((c for c in _DEST_COLS if c in columns), None)
    if origin_col is None or dest_col is None:
        return

    origins = df[origin_col].astype(str)
    dests = df[dest_col].astype(str)

    # A route to itself is its own tell; re-pick from the cities this table
    # already uses (keeps the vocabulary stable) or the known-city pool.
    same = (origins == dests).values
    if same.any():
        pool = [c for c in pd.unique(pd.concat([origins, dests])) if c in CITY_COORDS]
        if len(pool) > 1:
            for i in np.flatnonzero(same):
                alternatives = [c for c in pool if c != origins.iloc[i]]
                df.iloc[i, df.columns.get_loc(dest_col)] = rng.choice(alternatives)
            dests = df[dest_col].astype(str)

    known = origins.map(CITY_COORDS.__contains__).values & dests.map(
        CITY_COORDS.__contains__
    ).values
    if not known.any():
        return

    o_coords = np.array([CITY_COORDS[c] for c in origins.values[known]])
    d_coords = np.array([CITY_COORDS[c] for c in dests.values[known]])
    road_km = np.round(
        haversine_km(o_coords[:, 0], o_coords[:, 1], d_coords[:, 0], d_coords[:, 1])
        * ROAD_CIRCUITY,
        1,
    )

    distance_col = next((c for c in _DISTANCE_COLS if c in columns), None)
    if distance_col is not None:
        vals = df[distance_col].to_numpy(dtype=float, copy=True)
        vals[known] = road_km
        df[distance_col] = vals

    travel_col = next((c for c in _TRAVEL_COLS if c in columns), None)
    if travel_col is not None:
        vals = df[travel_col].to_numpy(dtype=float, copy=True)
        vals[known] = np.round(road_km / EFFECTIVE_SPEED_KMH + HANDLING_OVERHEAD_H, 1)
        df[travel_col] = vals


# ─── TEMPORAL RULES ───────────────────────────────────────────────────────────

def _fix_created_updated(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """updated_at must be >= created_at."""
    if "created_at" in columns and "updated_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        updated = pd.to_datetime(df["updated_at"], errors="coerce")
        mask = updated < created
        if mask.any():
            deltas = pd.to_timedelta(rng.integers(0, 7 * 24 * 60, size=mask.sum()), unit="m")
            updated.loc[mask] = created.loc[mask] + deltas
            df["updated_at"] = updated


def _fix_start_end_dates(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """end_date must be >= start_date."""
    if "start_date" in columns and "end_date" in columns:
        start = pd.to_datetime(df["start_date"], errors="coerce")
        end = pd.to_datetime(df["end_date"], errors="coerce")
        mask = end < start
        if mask.any():
            deltas = pd.to_timedelta(rng.integers(1, 365, size=mask.sum()), unit="D")
            end.loc[mask] = start.loc[mask] + deltas
        df["start_date"] = start
        df["end_date"] = end


def _fix_created_delivered(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """delivered_at must be after created_at. Only fixes rows where the order is violated."""
    if "created_at" in columns and "delivered_at" in columns:
        created = pd.to_datetime(df["created_at"], errors="coerce")
        delivered = pd.to_datetime(df["delivered_at"], errors="coerce")
        mask = delivered.notna() & created.notna() & (delivered <= created)
        if mask.any():
            deltas = pd.to_timedelta(
                rng.integers(1 * 24 * 60, 14 * 24 * 60, size=mask.sum()), unit="m"
            )
            delivered.loc[mask] = created.loc[mask] + deltas
            df["delivered_at"] = delivered


def _fix_delivered_requires_status(df: pd.DataFrame, columns: set[str]) -> None:
    """delivered_at should be null unless status is 'delivered'/'completed'."""
    if "status" in columns and "delivered_at" in columns:
        status = df["status"].astype(str).str.strip().str.lower()
        not_delivered = ~status.isin(DELIVERED_STATUSES)
        if not_delivered.any():
            df.loc[not_delivered, "delivered_at"] = None


# ─── MONETARY RULES ──────────────────────────────────────────────────────────

def _fix_cost_less_than_price(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Ensure cost < price. Only corrects rows where the constraint is violated or cost is missing."""
    if "cost" in columns and "price" in columns:
        price = pd.to_numeric(df["price"], errors="coerce").fillna(0)
        cost = pd.to_numeric(df["cost"], errors="coerce")
        violating = cost.isna() | (cost >= price)
        if violating.any():
            margin = rng.uniform(0.30, 0.70, size=violating.sum())
            df.loc[violating, "cost"] = np.round(price[violating].values * margin, 2)


def _fix_discount_cap(df: pd.DataFrame, columns: set[str]) -> None:
    """discount <= 30% of unit_price (or price)."""
    price_col = "unit_price" if "unit_price" in columns else ("price" if "price" in columns else None)
    if "discount" in columns and price_col:
        price = pd.to_numeric(df[price_col], errors="coerce").fillna(0)
        discount = pd.to_numeric(df["discount"], errors="coerce").fillna(0)
        max_discount = price * 0.30
        df["discount"] = np.round(np.minimum(discount, max_discount), 2)


def _fix_line_total(df: pd.DataFrame, columns: set[str]) -> None:
    """line_total = quantity * unit_price - discount."""
    if {"quantity", "unit_price", "line_total"}.issubset(columns):
        qty = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
        unit_price = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        discount = pd.to_numeric(df.get("discount", 0), errors="coerce").fillna(0)
        df["line_total"] = np.round(qty * unit_price - discount, 2).clip(lower=0)


def _fix_order_total(df: pd.DataFrame, columns: set[str]) -> None:
    """total = subtotal + tax + shipping_cost."""
    if {"subtotal", "total"}.issubset(columns):
        subtotal = pd.to_numeric(df["subtotal"], errors="coerce").fillna(0)
        tax = pd.to_numeric(df.get("tax", 0), errors="coerce").fillna(0) if "tax" in columns else 0
        shipping = pd.to_numeric(df.get("shipping_cost", 0), errors="coerce").fillna(0) if "shipping_cost" in columns else 0
        df["total"] = np.round(subtotal + tax + shipping, 2)
    elif {"quantity", "unit_price", "total"}.issubset(columns):
        qty = pd.to_numeric(df["quantity"], errors="coerce").fillna(1)
        unit_price = pd.to_numeric(df["unit_price"], errors="coerce").fillna(0)
        discount = pd.to_numeric(df.get("discount", 0), errors="coerce").fillna(0) if "discount" in columns else 0
        df["total"] = np.round(qty * unit_price - discount, 2).clip(lower=0)


def _apply_plan_price_mapping(df: pd.DataFrame, columns: set[str]) -> None:
    """Map plan names to standard prices."""
    if "plan" in columns and "price" in columns:
        plan_prices = {
            "free": 0.0, "basic": 9.99, "starter": 9.99,
            "premium": 19.99, "pro": 19.99, "professional": 29.99,
            "enterprise": 49.99, "business": 49.99, "unlimited": 99.99,
        }
        plan_series = df["plan"].astype(str).str.strip().str.lower()
        mapped = plan_series.map(plan_prices)
        df.loc[mapped.notna(), "price"] = mapped[mapped.notna()].astype(float)


# ─── IDENTITY RULES ──────────────────────────────────────────────────────────

def _fix_gender_name_coherence(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Make first names agree with a schema-declared ``gender``/``sex`` column.

    Direction matters: the declared gender DISTRIBUTION is part of the spec
    (it may carry explicit probabilities), so we keep gender and re-draw the
    first name — from the same culture as the row's surname, so the repair
    never reintroduces a "Wei Gonzalez". Non-binary/other genders keep their
    name as-is (any name is valid). Unknown first names (capsule/locale
    vocabularies we have no gender map for) are left untouched.
    """
    gender_col = next((c for c in ("gender", "sex") if c in columns), None)
    if gender_col is None:
        return

    if "first_name" in columns:
        firsts = df["first_name"].astype(str)
        name_col = "first_name"
    elif "name" in columns:
        name_series = df["name"].astype(str)
        if name_series.str.strip().str.split().str.len().ge(2).mean() < 0.6:
            return  # not personal names
        firsts = name_series.str.strip().str.split().str[0]
        name_col = "name"
    else:
        return

    declared = df[gender_col].astype(str).str.lower().str.strip()
    binary = declared.isin(["male", "female", "m", "f", "man", "woman"])
    declared_norm = declared.str[0].map({"m": "male", "f": "female"})

    name_gender = firsts.map(lambda n: lookup_gender(n) or "")
    mismatch = binary & (name_gender != "") & (name_gender != declared_norm)
    if not mismatch.any():
        return

    if "last_name" in columns:
        lasts = df.loc[mismatch, "last_name"].astype(str)
    elif name_col == "name":
        lasts = df.loc[mismatch, "name"].astype(str).str.strip().str.split().str[-1]
    else:
        lasts = pd.Series("", index=df.index[mismatch])

    cultures = lasts.map(lookup_surname_culture).values
    sampler = PersonSampler(rng)
    new_firsts = sampler.replacement_first_names(
        declared_norm[mismatch].values, cultures
    )

    if name_col == "first_name":
        df.loc[mismatch, "first_name"] = new_firsts
        if "name" in columns:
            last_part = df.loc[mismatch, "last_name"].astype(str) if "last_name" in columns else ""
            df.loc[mismatch, "name"] = [
                f"{f} {l}".strip() for f, l in zip(new_firsts, last_part)
            ]
    else:
        df.loc[mismatch, "name"] = [
            f"{f} {l}".strip() for f, l in zip(new_firsts, lasts)
        ]


def _fix_email_from_name(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Make ``email`` consistent with the person's name.

    A mismatched name/email (``"Brian Scott"`` with ``carol.stewart@...``) is the single
    most obvious tell that a dataset is fake, so this runs on every generation. It handles
    both the split-name schema (``first_name`` + ``last_name``) and the common single
    ``name`` column. Non-person ``name`` columns (e.g. a product or company ``name``) are
    left alone: we only rewrite when the values look like personal names.
    """
    if "email" not in columns:
        return

    domains = [
        "gmail.com", "yahoo.com", "outlook.com", "protonmail.com",
        "icloud.com", "hotmail.com", "aol.com", "mail.com",
    ]

    def _clean(part: str) -> str:
        return re.sub(r"[^a-z]", "", str(part).lower().strip())

    if {"first_name", "last_name"}.issubset(columns):
        firsts = df["first_name"].astype(str)
        lasts = df["last_name"].astype(str)
    elif "name" in columns:
        # Only treat as personal names if most rows look like "First Last" (2+ tokens).
        name_series = df["name"].astype(str)
        looks_personal = name_series.str.strip().str.split().str.len().ge(2).mean()
        if looks_personal < 0.6:
            return
        parts = name_series.str.strip().str.split()
        firsts = parts.str[0]
        lasts = parts.str[-1]
    else:
        return

    n = len(df)
    domain_choices = rng.choice(domains, size=n)
    separators = rng.choice([".", "_", ""], size=n, p=[0.6, 0.2, 0.2])
    emails = []
    for i in range(n):
        first = _clean(firsts.iloc[i])
        last = _clean(lasts.iloc[i])
        if not first and not last:
            emails.append(df.iloc[i]["email"])   # keep original if name is unusable
            continue
        stem = f"{first}{separators[i]}{last}".strip(".")
        emails.append(f"{stem}@{domain_choices[i]}")
    df["email"] = emails


_NAME_TO_POOL: Dict[str, str] = {}
for _pool, _names in PRODUCT_NAME_POOLS.items():
    for _n in _names:
        _NAME_TO_POOL[_n] = _pool


def _fix_category_from_product_name(df: pd.DataFrame, columns: set[str], table_name: str = "") -> None:
    """Make a product's ``category`` consistent with its ``name``.

    Names and categories are generated independently, so a "Portable Bluetooth Speaker"
    can land in "clothing" — an obvious tell that the data is fake. When the name comes
    from a known product pool, we set the category to that pool, mapped onto whatever
    category vocabulary the table actually uses (so the engine's "home" maps to a schema's
    "home & garden"). Only runs on product/item tables, and only rewrites rows whose name
    is a recognized product name; anything else is left untouched.
    """
    if "category" not in columns or "name" not in columns:
        return
    tl = table_name.lower()
    if "product" not in tl and "item" not in tl:
        return

    existing_cats = [str(c) for c in df["category"].dropna().unique()]
    if not existing_cats:
        return

    # Map each canonical pool ("electronics", "home", ...) to the closest category label
    # actually present in this table, so we never introduce an out-of-vocabulary value.
    def _closest_cat(pool: str) -> Optional[str]:
        pool_l = pool.lower()
        for c in existing_cats:
            cl = c.lower()
            if cl == pool_l or pool_l in cl or cl in pool_l:
                return c
        # token overlap (e.g. "home" vs "home & garden")
        for c in existing_cats:
            if pool_l in c.lower().split():
                return c
        return None

    pool_to_cat = {p: _closest_cat(p) for p in PRODUCT_NAME_POOLS}
    # Pools that this table's category vocabulary CAN represent.
    representable = {p for p, c in pool_to_cat.items() if c is not None}

    names = df["name"].tolist()
    cats = df["category"].tolist()
    for i, nm in enumerate(names):
        nm = str(nm)
        pool = _NAME_TO_POOL.get(nm)
        if pool is None:
            continue
        mapped = pool_to_cat.get(pool)
        if mapped is not None:
            # Name's pool is representable: set the category to match the name.
            cats[i] = mapped
        elif representable:
            # Name's pool (e.g. "food") has no category in this store. Rather than leave a
            # mismatch, swap the NAME to a product from a representable pool, deterministically
            # chosen from the row's current category so the (name, category) pair is coherent.
            cur = str(cats[i]).lower()
            target_pool = next(
                (p for p in representable
                 if p in cur or cur in p or p in cur.split()),
                sorted(representable)[0],
            )
            pool_names = PRODUCT_NAME_POOLS[target_pool]
            names[i] = pool_names[hash(nm) % len(pool_names)]
    df["name"] = names
    df["category"] = cats


def _fix_slug_from_name(df: pd.DataFrame, columns: set[str]) -> None:
    """Generate slug from name column."""
    if "slug" in columns and "name" in columns:
        df["slug"] = (
            df["name"].astype(str)
            .str.lower()
            .str.strip()
            .str.replace(r'[^a-z0-9\s-]', '', regex=True)
            .str.replace(r'\s+', '-', regex=True)
            .str.strip('-')
        )


# ─── STATUS-BASED RULES ──────────────────────────────────────────────────────

def _apply_status_end_date(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """Clear end_date for active statuses, set for inactive."""
    if "status" in columns and "end_date" in columns:
        status = df["status"].astype(str).str.strip().str.lower()
        end = pd.to_datetime(df["end_date"], errors="coerce")

        active_mask = status.isin(ACTIVE_STATUSES)
        if active_mask.any():
            end.loc[active_mask] = pd.NaT

        inactive_mask = status.isin(INACTIVE_STATUSES) & end.isna()
        if inactive_mask.any() and "start_date" in columns:
            start = pd.to_datetime(df["start_date"], errors="coerce")
            deltas = pd.to_timedelta(rng.integers(1, 365, size=inactive_mask.sum()), unit="D")
            end.loc[inactive_mask] = start.loc[inactive_mask] + deltas

        df["end_date"] = end
