"""
Realism rules for post-generation data adjustment.

These rules enforce cross-column mathematical and logical consistency
that the column-level generator cannot express. This is what separates
a realism engine from a random Faker.

Rules are applied conservatively — only when relevant columns exist.
"""

from __future__ import annotations

import re
import zlib
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
# Statuses that imply the order has physically shipped (so a ship timestamp is
# plausible). Anything earlier in the lifecycle should not carry a ship date.
SHIPPED_STATUSES = {"shipped", "dispatched", "in_transit", "out_for_delivery",
                    "delivered", "completed", "fulfilled", "returned", "refunded"}
# Reproducible "as of" date for age <- date_of_birth derivation when the table
# carries no other timestamp to anchor "now". Seed data ages as of this date.
_AGE_REFERENCE = "2025-06-01"

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

# Column names that hold a person's NAME by convention (movies.director,
# albums.artist, books.author) — routed to person_name, never job_title.
_PERSON_ROLE_COLUMNS = {
    "director", "author", "artist", "composer", "actor", "actress",
    "singer", "performer", "producer", "writer", "editor", "chef",
    "photographer", "illustrator", "narrator", "host", "speaker",
}

# Lookup/reference tables: `<head>_types` / `<head>_statuses` etc. Their label
# column must hold labels for the HEAD noun (property_types → House/Apartment),
# never generic tier words, and must be distinct.
_REF_TABLE_KIND_RE = re.compile(
    r"^(?:(?P<head>.+?)_)?(?P<kind>types?|status(?:es)?|categor(?:y|ies)|"
    r"tiers?|levels?|methods?|channels?|stages?|roles?|priorit(?:y|ies)|kinds?|"
    r"segments?|sizes?|grades?|ranks?|bands?|brackets?|classes)$",
    re.IGNORECASE,
)
def _is_text_dtype(series: "pd.Series") -> bool:
    """True for a string-holding column under any pandas config.

    Newer pandas / numpy-2 string inference gives string columns a ``str`` /
    ``string`` dtype rather than ``object``; a bare ``dtype == object`` check
    then silently skips them (the tier-monotonicity and state-machine label
    lookups both broke on CI this way). This accepts object and string dtypes.
    """
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


def _fuzzy_pool(pools: dict, head: str):
    """Resolve a lookup-table head noun against a pool dict, tolerating
    qualifier tokens: surge_pricing_event → surge_event pool.

    Order of attempts: exact key; pool key whose tokens all appear in the
    head IN ORDER (most tokens wins, then longest key); trailing-token
    suffixes of the head (pricing_event → event). Tokens compare with a
    trailing "s" stripped so plural qualifiers still match.
    """
    if not head:
        return None
    if head in pools:
        return pools[head]
    toks = [t.rstrip("s") for t in head.split("_") if t]
    best_key, best_score = None, (-1, 0, 0)
    for key in pools:
        ktoks = [t.rstrip("s") for t in key.split("_") if t]
        it = iter(toks)
        if all(kt in it for kt in ktoks):
            # English compounds are head-final: a delivery_driver is a
            # driver, so a key ending on the head's last token outranks one
            # matching earlier qualifiers; then most tokens, then longest.
            score = (int(ktoks[-1] == toks[-1]), len(ktoks), len(key))
            if score > best_score:
                best_key, best_score = key, score
    if best_key is not None:
        return pools[best_key]
    for i in range(1, len(toks)):
        cand = "_".join(toks[i:])
        if cand in pools:
            return pools[cand]
    return None


_REF_LABEL_COLUMNS = {"name", "label", "title", "status", "value", "state",
                      "type", "category", "kind", "description", "reason",
                      "method", "tier", "level", "segment"}
_REF_LABEL_SUFFIXES = ("_type", "_status", "_name", "_label", "_reason",
                       "_category", "_kind", "_method")

# Table names whose "title" column is a creative work, not a job.
_MEDIA_TABLE_HINTS = (
    "movie", "film", "show", "series", "episode", "book", "novel",
    "song", "track", "album", "podcast", "game", "course", "lesson",
    "article", "story", "poem", "play", "musical", "documentary", "video",
)

# Table names whose "title" column is a dish/recipe name, not a job.
_FOOD_TABLE_HINTS = ("recipe", "dish", "meal", "menu", "food")

# Table names whose "title" column is an event name; work_title is the
# closest pool (a job title here is a category error).
_EVENT_TABLE_HINTS = (
    "event", "conference", "webinar", "concert", "festival",
    "meetup", "seminar", "workshop", "exhibition",
)

# Table names that strongly imply the "name" column is an organisation name.
# Checked against table_name.lower() with substring matching.
_COMPANY_TABLE_HINTS = (
    "company", "companies", "vendor", "vendors", "brand", "brands",
    "organization", "organizations", "org", "orgs", "merchant", "merchants",
    "supplier", "suppliers", "employer", "employers",
    "firm", "store", "shop", "account", "accounts",
    "partner", "partners",
)

# Exact qualifiers (the token before "_name") that decide what a *_name column
# holds, ahead of any table context: business_name in a listings table is the
# business, seller_name in an orders table is the seller. "account"/"store"/
# "shop" are organisations (CRM accounts, retail stores); "account_holder" is
# the person. Matching is exact against the full qualifier, so short entries
# like "rep" cannot bleed into "report_name".
_PERSON_NAME_COL_QUALIFIERS = {
    "customer", "user", "full", "display", "contact",
    "holder", "legal", "person", "owner", "agent", "client", "member",
    "recipient", "employee", "buyer", "applicant", "sender", "driver",
    "account_holder", "manager", "cashier", "clerk", "teller", "supervisor",
    "seller", "assignee", "reviewer", "approver", "rep", "salesperson",
    "technician", "nurse", "doctor", "patient", "student", "teacher",
    "instructor", "passenger", "guest", "tenant", "borrower",
    "attendee", "participant", "subscriber", "donor", "player", "candidate",
}
_COMPANY_NAME_COL_QUALIFIERS = {
    "company", "vendor", "brand", "organization", "supplier",
    "employer", "business", "firm", "partner", "merchant",
    "account", "store", "shop", "agency", "carrier", "airline",
    "manufacturer", "distributor", "retailer", "wholesaler", "insurer",
    "publisher", "studio", "dealer", "dealership", "franchise",
}
# *_name columns naming a physical facility — composed as "{City} {Kind}"
# ("Riverside Hotel", "Salem Warehouse"), which reads right where a corporate
# name ("Vertex Labs Group") or a tier label ("Pro") would not.
_FACILITY_NAME_COL_QUALIFIERS = {
    "warehouse", "branch", "facility", "depot", "hub", "plant", "terminal",
    "station", "campus", "office", "hotel", "clinic", "hospital", "pharmacy",
    "bank", "school", "university", "library", "airport", "gym",
}
_TEAM_NAME_WORDS = [
    "Platform", "Growth", "Data", "Mobile", "Infrastructure", "Design",
    "Payments", "Search", "Analytics", "Core", "Security", "Support",
    "Revenue", "Onboarding", "Billing", "Frontend", "Backend", "Marketing",
    "Sales", "Success",
]

# Generic, domain-neutral labels for a lookup table that arrived without
# inline_data — far better than person names or lorem sentences for a 3-20 row
# dimension table (plan tiers, statuses, types).
CATEGORY_LABELS = [
    "Standard", "Basic", "Premium", "Pro", "Enterprise", "Starter", "Plus",
    "Lite", "Advanced", "Core", "Team", "Business", "Free", "Custom", "Trial",
    "Active", "Inactive", "Pending", "Default", "Primary", "Secondary",
    "General", "Essential", "Professional", "Ultimate", "Growth", "Scale",
]

# Industry / vertical sector names for "industry", "sector", "vertical" columns.
_INDUSTRY_LABELS = [
    "SaaS", "FinTech", "HealthTech", "EdTech", "E-commerce", "Retail",
    "Healthcare", "Finance", "Manufacturing", "Logistics", "Media",
    "Real Estate", "Consulting", "Legal", "Marketing", "HR Tech",
    "Cybersecurity", "Analytics", "AI / ML", "Biotech", "CleanTech",
    "InsurTech", "PropTech", "Gaming", "Travel", "Food & Beverage",
    "Telecommunications", "Energy", "Agriculture", "Automotive",
]

# Event / action type labels for "event_name", "event_type", "action_name" columns.
_EVENT_TYPE_LABELS = [
    "page_view", "click", "signup", "login", "logout", "purchase", "checkout",
    "add_to_cart", "search", "download", "upload", "share", "invite",
    "subscription_created", "subscription_updated", "subscription_cancelled",
    "payment_succeeded", "payment_failed", "trial_started", "trial_converted",
    "feature_used", "onboarding_completed", "churn", "referral",
]

# Payment-method labels for "method"/"payment_method" columns (common in
# auto-created lookup tables the LLM leaves without inline_data).
_PAYMENT_METHOD_LABELS = [
    "Credit Card", "Debit Card", "PayPal", "Bank Transfer", "Apple Pay",
    "Google Pay", "Wire Transfer", "ACH", "Cash on Delivery", "Gift Card",
    "Cryptocurrency", "Klarna", "Stripe", "Venmo",
]

# Short reason labels for "reason"/"*_reason" columns — never business sentences.
_REASON_LABELS = [
    "Too expensive", "Switched to competitor", "No longer needed",
    "Missing features", "Poor customer support", "Technical issues",
    "Found a better alternative", "Budget cuts", "Low usage",
    "Hard to use", "Billing problem", "Relocated", "Service discontinued",
    "Unsatisfied with quality", "Other",
]

_CHANNEL_LABELS = [
    "Email", "Organic Search", "Paid Search", "Social Media", "Direct",
    "Referral", "Affiliate", "Display Ads", "YouTube", "Content Marketing",
    "Influencer", "Trade Show", "Newsletter", "Podcast", "Cold Outreach",
]

_DEPARTMENT_LABELS = [
    "Engineering", "Product", "Sales", "Marketing", "Customer Success",
    "Finance", "Legal", "HR", "Operations", "Data", "Security", "Design",
    "Support", "Research", "Business Development",
]

_REGION_LABELS = [
    "North America", "EMEA", "APAC", "LATAM", "US East", "US West",
    "US Central", "Europe", "Asia Pacific", "Middle East", "Africa",
    "Southeast Asia", "ANZ",
]

_CURRENCY_CODES = [
    "USD", "EUR", "GBP", "JPY", "CAD", "AUD", "CHF", "CNY", "INR", "BRL",
    "MXN", "KRW", "SGD", "HKD", "NOK", "SEK", "DKK", "NZD", "ZAR", "AED",
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
        domain: Optional[str] = None,
    ):
        self.rng = rng or np.random.default_rng(42)
        self.capsule = capsule
        self.domain = (domain or "").lower()
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

    _MEDICAL_DOMAINS = ("health", "hospital", "medical", "clinic", "pharma", "care")

    def _is_medical_domain(self) -> bool:
        return any(h in self.domain for h in self._MEDICAL_DOMAINS)

    def _reference_table_labels(
        self, column_name: str, table_name: str, size: int
    ) -> Optional[np.ndarray]:
        """Distinct, head-noun-appropriate labels for lookup tables, or None.

        ``property_types.name`` → House/Apartment/Condo…, ``listing_statuses.
        status`` → Active/Pending/Sold… Generic pools cover unknown heads.
        Only fires for label-ish columns in small reference tables.
        """
        col_l = column_name.lower()
        if size > 50 or (
            col_l not in _REF_LABEL_COLUMNS
            and not col_l.endswith(_REF_LABEL_SUFFIXES)
        ):
            return None
        m = _REF_TABLE_KIND_RE.match(table_name.lower().strip())
        if not m:
            return None
        from misata.vocab_seeds import (
            GENERIC_CHANNELS, GENERIC_SEGMENTS, GENERIC_SIZES,
            GENERIC_STATUSES, GENERIC_TIERS, REFERENCE_CHANNEL_POOLS,
            REFERENCE_SEGMENT_POOLS, REFERENCE_SIZE_POOLS,
            REFERENCE_STATUS_POOLS, REFERENCE_TIER_POOLS, REFERENCE_TYPE_POOLS,
        )
        head = (m.group("head") or "").rstrip("s")
        kind = m.group("kind").lower()
        if kind.startswith("channel"):
            pool = _fuzzy_pool(REFERENCE_CHANNEL_POOLS, head) or GENERIC_CHANNELS
        elif kind.startswith("status") or kind.startswith("stage"):
            pool = _fuzzy_pool(REFERENCE_STATUS_POOLS, head) or GENERIC_STATUSES
        elif kind.startswith("segment"):
            pool = _fuzzy_pool(REFERENCE_SEGMENT_POOLS, head) or GENERIC_SEGMENTS
        elif kind.startswith("size"):
            pool = _fuzzy_pool(REFERENCE_SIZE_POOLS, head) or GENERIC_SIZES
        elif kind.startswith(("tier", "level", "grade", "rank", "band", "bracket")):
            pool = _fuzzy_pool(REFERENCE_TIER_POOLS, head) or GENERIC_TIERS
        else:
            pool = _fuzzy_pool(REFERENCE_TYPE_POOLS, head)
            if pool is None:
                pool = self._vocabulary("category_label", CATEGORY_LABELS)
        pool = list(pool)
        if size <= len(pool):
            return self.rng.choice(pool, size=size, replace=False)
        # More rows than labels: use every label once, then repeat.
        reps = np.tile(pool, size // len(pool) + 1)[:size]
        return np.array(reps)

    def generate(
        self,
        column_name: str,
        table_name: str,
        size: int,
        semantic_type: Optional[str] = None,
        table_data: Optional[pd.DataFrame] = None,
    ) -> np.ndarray:
        # Lookup-table labels win over everything: a reference table's label
        # column is an enumeration, not a distribution.
        ref_labels = self._reference_table_labels(column_name, table_name, size)
        if ref_labels is not None:
            return ref_labels

        # A specific inference (blood_type, lab_test, department, …) beats a
        # GENERIC semantic passed by the caller ("name"/"text"): the simulator's
        # fallback routing must not shadow clinical/reference columns.
        if semantic_type in (None, "", "name", "sentence", "text", "word"):
            semantic = self._infer_semantic(column_name, table_name) or semantic_type or "name"
        else:
            semantic = semantic_type

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
            # Guard: a bare "name"/"full_name"/"display_name" in a non-person
            # table is almost certainly an LLM mislabelling (plans.name, etc.).
            # Column qualifiers or person-table context override this guard.
            _BARE_NAME_COLS = {"name", "full_name", "display_name"}
            _tbl_pn = table_name.lower()
            if (
                column_name.lower() in _BARE_NAME_COLS
                and not any(p in _tbl_pn for p in _PERSON_TABLE_HINTS)
            ):
                if any(c in _tbl_pn for c in _COMPANY_TABLE_HINTS):
                    return self.generate(column_name, table_name, size, "company_name")
                return self._labels("category_label", CATEGORY_LABELS, size)
            if faker and not _has_capsule_vocab("first_name"):
                return np.array([faker.name() for _ in range(size)])
            if _has_capsule_vocab("first_name"):
                first = self.rng.choice(self._vocabulary("first_name", FIRST_NAMES), size=size)
                last = self.rng.choice(self._vocabulary("last_name", LAST_NAMES), size=size)
                return np.array([f"{f} {l}" for f, l in zip(first, last)])
            return self._person_frame(table_name, size)["full"]
        if semantic == "name":
            # "name" is ambiguous — column qualifier + table name together decide.
            # "customer_name", "full_name", "display_name" → person even in non-person tables.
            # "name" in companies/vendors/orgs → company name.
            # "name" in products/items → product name.
            # "name" in plans/statuses/lookup tables → short tier label.
            # "account"/"store"/"shop" are organisations (CRM accounts, retail
            # stores) — account_holder stays a person via "holder".
            _PERSON_NAME_QUALIFIERS = {
                "customer", "user", "full", "display", "contact",
                "holder", "legal", "person", "owner", "agent", "client", "member",
            }
            _COMPANY_NAME_QUALIFIERS = ("account", "store", "shop", "company",
                                        "vendor", "brand", "merchant")
            _PRODUCT_TABLE_HINTS = (
                "product", "products", "item", "items", "listing", "listings",
                "catalog", "catalogue", "merchandise", "inventory", "sku", "offer",
            )
            _tbl = table_name.lower()
            _col_lower = column_name.lower()
            _col_has_person_qualifier = any(q in _col_lower for q in _PERSON_NAME_QUALIFIERS)
            _col_has_company_qualifier = any(q in _col_lower for q in _COMPANY_NAME_QUALIFIERS)
            if _col_has_person_qualifier or (
                not _col_has_company_qualifier
                and any(p in _tbl for p in _PERSON_TABLE_HINTS)
            ):
                if faker and not _has_capsule_vocab("first_name"):
                    return np.array([faker.name() for _ in range(size)])
                return self._person_frame(table_name, size)["full"]
            if _col_has_company_qualifier or any(c in _tbl for c in _COMPANY_TABLE_HINTS):
                return self.generate(column_name, table_name, size, "company_name")
            if any(pt in _tbl for pt in _PRODUCT_TABLE_HINTS):
                return self.generate(column_name, table_name, size, "product_name")
            if "event" in _col_lower or "action" in _col_lower:
                return self.generate(column_name, table_name, size, "event_type")
            return self._labels("category_label", CATEGORY_LABELS, size)
        if semantic == "industry":
            return self._labels("industry", _INDUSTRY_LABELS, size)
        if semantic == "event_type":
            return self._labels("event_type", _EVENT_TYPE_LABELS, size)
        if semantic == "payment_method":
            return self._labels("payment_method", _PAYMENT_METHOD_LABELS, size)
        if semantic == "reason":
            return self._labels("reason", _REASON_LABELS, size)
        if semantic == "channel":
            return self._labels("channel", _CHANNEL_LABELS, size)
        if semantic == "department":
            if self._is_medical_domain():
                # A hospital's departments are clinical (capsule vocab bypassed).
                from misata.vocab_seeds import MEDICAL_DEPARTMENTS
                pool = list(MEDICAL_DEPARTMENTS)
                if 0 < size <= len(pool):
                    return self.rng.choice(pool, size=size, replace=False)
                return self.rng.choice(pool, size=size)
            return self._labels("department", _DEPARTMENT_LABELS, size)
        if semantic == "region":
            return self._labels("region", _REGION_LABELS, size)
        if semantic == "currency":
            return self._labels("currency", _CURRENCY_CODES, size)
        if semantic == "mcc_code":
            # Real ISO 18245 merchant category codes — random 4-digit numbers
            # are instantly wrong to anyone in payments (5411 is grocery).
            _MCC = ["5411", "5812", "5814", "5541", "4111", "5912", "5999",
                    "5311", "7011", "5732", "4899", "5942", "5651", "5945",
                    "4121", "5813", "5921", "7832", "8011", "8062", "4816",
                    "5967", "6011", "4814", "5122"]
            return self.rng.choice(_MCC, size=size)
        if semantic == "vehicle_make":
            from misata.vocab_seeds import VEHICLE_MODELS_BY_MAKE
            makes = [m.title() if m != "bmw" and m != "gmc" else m.upper()
                     for m in VEHICLE_MODELS_BY_MAKE]
            return self.rng.choice(makes, size=size)
        if semantic == "vehicle_model":
            from misata.vocab_seeds import VEHICLE_MODELS_BY_MAKE
            # Coherence first: when the row already has a make, the model
            # must belong to it (Toyota rows get Camry, never an F-150).
            if table_data is not None:
                _make_col = next(
                    (c for c in table_data.columns if c.lower() in ("make", "manufacturer", "brand", "vehicle_make")),
                    None,
                )
                if _make_col is not None:
                    row_makes = table_data[_make_col].astype(str).values[:size]
                    out = []
                    for mk in row_makes:
                        pool = VEHICLE_MODELS_BY_MAKE.get(mk.strip().lower())
                        if pool is None:
                            pool = [p for models in VEHICLE_MODELS_BY_MAKE.values() for p in models]
                        out.append(self.rng.choice(pool))
                    result = np.array(out)
                    if len(result) < size:
                        pad = self.rng.choice(result, size=size - len(result))
                        result = np.concatenate([result, pad])
                    return result
            all_models = [p for models in VEHICLE_MODELS_BY_MAKE.values() for p in models]
            return self.rng.choice(all_models, size=size)
        if semantic == "reference_code":
            # Alphanumeric identifier, uniform shape per column. Carrier-style
            # for tracking columns, generic prefixed code otherwise.
            n = str(column_name).lower()
            letters = np.array(list("ABCDEFGHJKLMNPQRSTUVWXYZ"))
            if "track" in n or "awb" in n or "waybill" in n or "shipment" in n:
                out = [f"1Z{''.join(self.rng.choice(letters, 3))}"
                       f"{''.join(str(self.rng.integers(0, 10)) for _ in range(13)) }"
                       for _ in range(size)]
                return np.array(out)
            prefix = ("INV" if "invoice" in n else "SKU" if "sku" in n
                      else "ORD" if "order" in n else "CNF" if "conf" in n
                      else "REF")
            out = [f"{prefix}-{''.join(str(self.rng.integers(0, 10)) for _ in range(8))}"
                   for _ in range(size)]
            return np.array(out)
        if semantic == "license_plate":
            # US-style plate shapes; one shape per column keeps a table uniform.
            _shapes = ["LLL-DDDD", "DLLL-DDD", "LLL DDDD", "DDD-LLLL"]
            shape = _shapes[zlib.crc32(f"{table_name}.{column_name}".encode()) % len(_shapes)]
            letters = np.array(list("ABCDEFGHJKLMNPRSTUVWXYZ"))
            out = []
            for _ in range(size):
                out.append("".join(
                    self.rng.choice(letters) if ch == "L"
                    else str(self.rng.integers(0, 10)) if ch == "D"
                    else ch
                    for ch in shape
                ))
            return np.array(out)
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
        if semantic == "facility_name":
            # "{City} {Kind}": warehouse_name → "Salem Warehouse",
            # hotel_name → "Riverside Hotel".
            _col = column_name.lower()
            _kind = (_col[:-5].split("_")[-1] if _col.endswith("_name")
                     else "facility").title()
            cities = self.generate(column_name, table_name, size, "city")
            return np.array([f"{c} {_kind}" for c in cities])
        if semantic == "team_name":
            return np.array([
                f"{w} Team" for w in self.rng.choice(_TEAM_NAME_WORDS, size=size)
            ])
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
            # Cross-column coherence FIRST: when the same table carries a
            # country column, each row's city must belong to that row's
            # country (Philadelphia cannot sit in Canada). The locale pack
            # only decides for tables with no country context.
            if table_data is not None:
                _country_col = next(
                    (c for c in table_data.columns
                     if c.lower() == "country" or c.lower().endswith("_country")),
                    None,
                )
                if _country_col is not None:
                    _row_countries = table_data[_country_col].astype(str).values
                    _known = [c for c in set(_row_countries) if c in COUNTRY_CITIES]
                    if _known:
                        return np.array([
                            self.rng.choice(COUNTRY_CITIES.get(
                                country, COUNTRY_CITIES["United States"]))
                            for country in _row_countries
                        ])
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
        if semantic in ("url", "domain"):
            slugs = self._slugify(self.generate(column_name, table_name, size, "company_name"))
            return np.array([f"https://www.{slug}.com" for slug in slugs])
        if semantic == "slug_source":
            words = self.rng.choice(["modern", "prime", "atlas", "core", "blue", "summit"], size=(size, 2))
            return np.array([f"{left}-{right}" for left, right in words])
        if semantic == "category_label":
            return self._labels("category_label", CATEGORY_LABELS, size)
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
        if semantic == "genre":
            return self._generate_genre(table_name, size)
        if semantic == "cuisine":
            from misata.vocab_seeds import CUISINES
            return self._labels("cuisine", CUISINES, size)
        if semantic == "ingredient_list":
            return self._generate_ingredient_list(size=size)
        if semantic == "work_title":
            return self._generate_work_title(size=size)
        if semantic == "plot_summary":
            return self._generate_plot_summary(size=size)
        if semantic in ("office_department", "department"):
            from misata.vocab_seeds import MEDICAL_DEPARTMENTS, OFFICE_DEPARTMENTS
            if self._is_medical_domain():
                # Bypass capsule vocab: a hospital's departments are clinical.
                pool = list(MEDICAL_DEPARTMENTS)
                if 0 < size <= len(pool):
                    return self.rng.choice(pool, size=size, replace=False)
                return self.rng.choice(pool, size=size)
            return self._labels("department", OFFICE_DEPARTMENTS, size)
        if semantic == "blood_type":
            from misata.vocab_seeds import BLOOD_TYPES, BLOOD_TYPE_WEIGHTS
            return self.rng.choice(BLOOD_TYPES, size=size, p=BLOOD_TYPE_WEIGHTS)
        if semantic == "medication":
            from misata.vocab_seeds import MEDICATIONS
            return self._labels("medication", MEDICATIONS, size)
        if semantic == "dosage":
            from misata.vocab_seeds import DOSAGE_AMOUNTS
            return self.rng.choice(DOSAGE_AMOUNTS, size=size)
        if semantic == "admission_type":
            from misata.vocab_seeds import ADMISSION_TYPES
            return self._labels("admission_type", ADMISSION_TYPES, size)
        if semantic == "diagnosis":
            from misata.vocab_seeds import COMMON_DIAGNOSES
            return self._labels("diagnosis", COMMON_DIAGNOSES, size)
        if semantic == "discharge_status":
            from misata.vocab_seeds import DISCHARGE_STATUSES
            return self._labels("discharge_status", DISCHARGE_STATUSES, size)
        if semantic == "medical_specialty":
            from misata.vocab_seeds import MEDICAL_SPECIALTIES
            return self._labels("medical_specialty", MEDICAL_SPECIALTIES, size)
        if semantic == "lab_test":
            from misata.vocab_seeds import LAB_TESTS
            return self._labels("lab_test", LAB_TESTS, size)
        if semantic == "lab_unit":
            from misata.vocab_seeds import LAB_UNITS
            return self.rng.choice(LAB_UNITS, size=size)
        if semantic == "surge_reason":
            from misata.vocab_seeds import SURGE_REASONS
            return self.rng.choice(SURGE_REASONS, size=size)
        if semantic == "cancellation_reason":
            from misata.vocab_seeds import CANCELLATION_REASONS
            return self.rng.choice(CANCELLATION_REASONS, size=size)
        if semantic == "med_frequency":
            from misata.vocab_seeds import MED_FREQUENCIES
            return self.rng.choice(MED_FREQUENCIES, size=size)

        # Unknown semantic token from the caller (LLMs invent text_types like
        # "make" or "model"): re-infer from the column name before falling
        # back to filler sentences.
        inferred = self._infer_semantic(column_name, table_name)
        if inferred and inferred != semantic:
            return self.generate(column_name, table_name, size, inferred, table_data)

        return np.array([
            self.rng.choice(self._vocabulary("product_description", PRODUCT_DESCRIPTION_TEMPLATES))
            for _ in range(size)
        ])

    # ── Media / food / creative-work generators (0.8.1.15) ──────────────────

    _MUSIC_TABLE_HINTS = ("song", "track", "album", "artist", "band",
                          "playlist", "music", "record")
    _BOOK_TABLE_HINTS = ("book", "novel", "publication", "library", "author")

    def _generate_genre(self, table_name: str, size: int) -> np.ndarray:
        """Genre pool chosen by table context: music, book, or film."""
        from misata.vocab_seeds import BOOK_GENRES, FILM_GENRES, MUSIC_GENRES
        tbl = table_name.lower()
        if any(h in tbl for h in self._MUSIC_TABLE_HINTS):
            return self._labels("genre", MUSIC_GENRES, size)
        if any(h in tbl for h in self._BOOK_TABLE_HINTS):
            return self._labels("genre", BOOK_GENRES, size)
        return self._labels("genre", FILM_GENRES, size)

    def _generate_ingredient_list(self, *, size: int) -> np.ndarray:
        """3–6 distinct ingredients joined as a comma list per row."""
        from misata.vocab_seeds import INGREDIENTS
        pool = list(self._vocabulary("ingredient", INGREDIENTS))
        out = []
        for _ in range(size):
            n = int(self.rng.integers(3, 7))
            picks = self.rng.choice(pool, size=min(n, len(pool)), replace=False)
            out.append(", ".join(picks))
        return np.array(out)

    def _generate_work_title(self, *, size: int) -> np.ndarray:
        """Compositional creative-work titles (film/book/song/course)."""
        from misata.vocab_seeds import (
            WORK_TITLE_ADJECTIVES, WORK_TITLE_NOUNS, WORK_TITLE_PATTERNS,
        )
        out = []
        for _ in range(size):
            pattern = self.rng.choice(WORK_TITLE_PATTERNS)
            noun = self.rng.choice(WORK_TITLE_NOUNS)
            noun2 = self.rng.choice([n for n in WORK_TITLE_NOUNS if n != noun])
            adj = self.rng.choice(WORK_TITLE_ADJECTIVES)
            out.append(pattern.format(adj=adj, noun=noun, noun2=noun2))
        return np.array(out)

    def _generate_plot_summary(self, *, size: int) -> np.ndarray:
        """Grammar-composed one-line plot synopses."""
        from misata.vocab_seeds import (
            PLOT_GOALS, PLOT_INCIDENTS, PLOT_PROTAGONISTS, PLOT_STAKES,
        )
        frames = (
            "When {incident}, {protagonist} must {goal} {stakes}.",
            "{protagonist_cap} sets out to {goal} {stakes}.",
            "After {incident}, {protagonist} has one chance to {goal}.",
        )
        out = []
        for _ in range(size):
            frame = self.rng.choice(frames)
            protagonist = str(self.rng.choice(PLOT_PROTAGONISTS))
            out.append(frame.format(
                incident=self.rng.choice(PLOT_INCIDENTS),
                protagonist=protagonist,
                protagonist_cap=protagonist[0].upper() + protagonist[1:],
                goal=self.rng.choice(PLOT_GOALS),
                stakes=self.rng.choice(PLOT_STAKES),
            ))
        return np.array(out)

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
        # Person-role columns hold the person's NAME, not a job title.
        if name in _PERSON_ROLE_COLUMNS or any(
            name.endswith("_" + role) for role in _PERSON_ROLE_COLUMNS
        ):
            return "person_name"
        # "title" in a creative-work table is the work's title, not a job.
        _is_media_table = any(h in table for h in _MEDIA_TABLE_HINTS)
        if name in ("title", "work_title") and _is_media_table:
            return "work_title"
        # "title" in a recipes/dishes/meals table is the dish name, not a job.
        if name in ("title", "recipe_title", "dish_title", "meal_title") and any(
            h in table for h in _FOOD_TABLE_HINTS
        ):
            return "menu_item"
        # "title" in a product/listing table is the product's name.
        if name == "title" and any(
            h in table for h in ("product", "listing", "item", "sku", "catalog")
        ):
            return "product_name"
        # A ticket's "title"/"subject" is the one-line issue, not a job.
        if name in ("title", "subject") and ("ticket" in table or "issue" in table):
            return "support_ticket"
        if name == "title" and any(h in table for h in _EVENT_TABLE_HINTS):
            return "work_title"
        if "genre" in name:
            return "genre"
        if "cuisine" in name:
            return "cuisine"
        if name in ("ingredient", "ingredients", "ingredient_list"):
            return "ingredient_list"
        if name in ("plot", "plot_summary", "synopsis", "storyline", "logline") or (
            name in ("summary", "overview") and _is_media_table
        ):
            return "plot_summary"
        # Clinical columns are unambiguous regardless of domain.
        if name in ("blood_type", "blood_group"):
            return "blood_type"
        if name in ("medication", "medication_name", "drug", "drug_name"):
            return "medication"
        if name in ("dosage", "dose"):
            return "dosage"
        if name in ("admission_type", "admission_reason"):
            return "admission_type"
        if name in ("diagnosis", "primary_diagnosis", "condition", "medical_condition"):
            return "diagnosis"
        if name in ("discharge_status", "discharge_disposition"):
            return "discharge_status"
        if name in ("specialty", "specialization", "speciality"):
            return "medical_specialty"
        _is_lab_table = any(h in table for h in ("lab", "test", "result", "panel"))
        if name in ("test_name", "lab_test", "panel_name") or (name == "name" and _is_lab_table):
            return "lab_test"
        if name in ("unit", "units", "result_unit") and _is_lab_table:
            return "lab_unit"
        if name == "frequency" and any(h in table for h in ("prescription", "medication", "dosage", "rx")):
            return "med_frequency"
        # Vehicle columns: model must be a real model (coherent with make),
        # plates must be plate codes — neither may fall to sentence filler.
        _is_vehicle_table = any(h in table for h in ("vehicle", "car", "fleet", "truck", "automobile"))
        if name in ("license_plate", "plate_number", "number_plate", "plate",
                    "registration_plate", "reg_plate", "vehicle_plate"):
            return "license_plate"
        # Tracking / reference / confirmation codes are alphanumeric identifiers,
        # never prose. Catches tracking_number, reference_number, sku,
        # confirmation_code, order_number, invoice_number, awb, etc.
        _code_exact = {
            "tracking_number", "tracking_id", "tracking_code", "reference_number",
            "reference_code", "reference_no", "ref_number", "confirmation_number",
            "confirmation_code", "order_number", "invoice_number", "invoice_no",
            "serial_number", "serial_no", "sku", "sku_code", "awb",
            "waybill_number", "shipment_number", "booking_reference", "pnr",
            "voucher_code", "coupon_code", "promo_code", "transaction_reference",
        }
        # Only the explicit set and unambiguous suffixes. A broad "_code" match
        # would hijack columns with real vocabularies (mcc_code, currency_code,
        # country_code) that are handled elsewhere.
        if name in _code_exact or name.endswith(("_tracking_number",
                                                 "_reference_number")):
            return "reference_code"
        if name in ("model", "vehicle_model", "car_model", "make_model") and (
            _is_vehicle_table or name != "model"
        ):
            return "vehicle_model"
        if name == "make" and _is_vehicle_table:
            return "vehicle_make"
        if "reason" in name:
            if "surge" in name or "surge" in table:
                return "surge_reason"
            if "cancel" in name or "cancel" in table:
                return "cancellation_reason"
        if name in ("department", "dept", "division", "business_unit") or name.endswith("_department"):
            return "department"
        if name == "name" and table in ("departments", "department", "wards") and self._is_medical_domain():
            return "department"
        if name in ("location", "office_location", "branch_location", "site_location"):
            return "city"
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
        # "tel" must be its own token — "hotel_name" is not a telephone.
        if "phone" in name or "mobile" in name or {"tel", "telephone"} & set(name.split("_")):
            return "phone_number"
        if name in ("domain", "website", "site", "homepage") or name.endswith("_domain") or name.endswith("_url"):
            return "url"
        if name in ("national_id", "ssn", "cpf", "aadhaar", "nid", "tax_id") or "national_id" in name:
            return "national_id"
        if name in ("mcc", "mcc_code", "merchant_category_code"):
            return "mcc_code"
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
        if name.endswith("_name"):
            # The exact qualifier decides before any table catchall —
            # business_name in a listings table is the business, not a listing.
            _q = name[:-5]
            if _q in _PERSON_NAME_COL_QUALIFIERS or _q in _PERSON_ROLE_COLUMNS:
                return "person_name"
            if _q in _COMPANY_NAME_COL_QUALIFIERS:
                return "company_name"
            if _q in _FACILITY_NAME_COL_QUALIFIERS:
                return "facility_name"
            if _q in ("product", "item", "sku", "listing"):
                return "product_name"
            if _q in ("restaurant", "cafe", "diner"):
                return "restaurant_name"
            if _q == "team":
                return "team_name"
        if "product" in table or "item" in table or "listing" in table:
            return "product_name"
        if name in ("name", "label") and table in ("departments", "department", "wards"):
            return "department"
        if name in ("name", "full_name", "display_name"):
            # Context-dependent: person table → person name, company/org table →
            # company name, product table → product name, else → tier label.
            if any(p in table for p in _PERSON_TABLE_HINTS):
                return "person_name"
            if any(c in table for c in _COMPANY_TABLE_HINTS):
                return "company_name"
            if any(pt in table for pt in (
                "product", "products", "item", "items", "listing",
                "catalog", "catalogue", "inventory", "sku",
            )):
                return "product_name"
            return "category_label"
        if name.endswith("_name"):
            # The exact qualifier was already checked (before the product
            # catchall above) — only table context is left to consult.
            # An event/action token in the column itself outranks it:
            # user_actions.action_name is an event label, not a user.
            # Token match — "transactions" must not read as "action".
            _col_toks = {t.rstrip("s") for t in name.split("_")}
            if {"event", "action", "activity"} & _col_toks:
                return "event_type"
            if any(p in table for p in _PERSON_TABLE_HINTS):
                return "person_name"
            if any(c in table for c in _COMPANY_TABLE_HINTS):
                return "company_name"
            _tbl_toks = {t.rstrip("s") for t in table.split("_")}
            if {"event", "action", "activity"} & _tbl_toks:
                return "event_type"
            return "category_label"
        # Payment-method and reason lookup columns — extremely common in
        # auto-created reference tables, and the worst offenders when they fall to
        # the lorem-sentence path ("payment method: Client requested a follow-up").
        if name in ("method", "payment_method", "pay_method", "billing_method", "tender"):
            return "payment_method"
        if name.endswith("_method"):
            return "category_label"  # shipping_method etc. → short label, not a sentence
        if name == "reason" or name.endswith("_reason"):
            return "reason"
        if name in ("channel", "acquisition_channel", "marketing_channel", "source_channel", "utm_medium"):
            return "channel"
        if name in ("department", "dept", "division", "business_unit"):
            return "department"
        if name in ("region", "territory", "zone", "district", "geo", "geography"):
            return "region"
        if name in ("currency", "currency_code", "pay_currency", "invoice_currency"):
            return "currency"
        # Short categorical-label columns: a free-text status/type/tier should be
        # a label, not a lorem sentence (these usually arrive as enums/inline_data;
        # this is the fallback when they don't).
        if name in (
            "status", "type", "category", "tier", "level", "kind", "stage",
            "label", "grade", "class", "mode", "priority", "severity", "plan",
            "source", "medium",
        ):
            return "category_label"
        if name in ("industry", "sector", "vertical", "niche", "market", "segment"):
            return "industry"
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
            elif token == "#":
                # Spreadsheet/Faker-style digit placeholder ("AB-####"), the
                # syntax no-code and studio users reach for first.
                char_type = "digit"
                i += 1
            elif token == "?" :
                # Faker-style uppercase-letter placeholder ("??-1234").
                char_type = "letter"
                i += 1
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

    def _labels(self, name: str, fallback: Iterable[str], size: int) -> np.ndarray:
        """Draw ``size`` short labels from a vocabulary. When the request fits the
        vocabulary (a small lookup / reference table, e.g. 4 payment methods),
        sample WITHOUT replacement so the labels are distinct — a 4-row
        payment_methods table shouldn't repeat "Credit Card". Larger fact-table
        columns keep sampling with replacement to preserve a distribution."""
        vocab = self._vocabulary(name, fallback)
        if 0 < size <= len(vocab):
            return self.rng.choice(vocab, size=size, replace=False)
        return self.rng.choice(vocab, size=size)


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


# Causal order of lifecycle timestamps found on one row. A row's date columns
# are sorted so the earliest real value lands on the earliest-ranked column,
# which kills impossible orderings (an order that "shipped" before it was
# placed) while leaving each column's marginal distribution intact. Ordering
# covers the obvious e-commerce / SaaS / logistics lifecycles a user seeds.
# NOTE: forward-looking columns (due, expires, valid_until) are intentionally
# absent — they legitimately post-date everything and are left untouched.
_TIME_CHAIN_ORDER = (
    # account / record birth
    "created", "registered", "signup", "sign_up", "joined", "onboarded",
    "requested", "request", "submitted", "applied",
    # commerce: place → pay → approve
    "placed", "ordered", "order", "booking", "booked", "reserved",
    "quoted", "invoiced", "billed", "paid", "payment", "captured",
    "approved", "authorized", "confirmed", "accepted",
    # fulfilment: prepare → dispatch → transit
    "start", "begin", "processing", "prepared", "packed", "ready",
    "dispatch", "dispatched", "fulfilled", "shipped", "shipment", "sent",
    "pickup", "pick_up", "picked", "collected", "loaded", "scanned",
    "departure", "departed", "in_transit", "transit", "out_for_delivery",
    # arrival / completion
    "arrival", "arrived", "dropoff", "delivered", "received", "installed",
    "activated", "checkin", "check_in", "checkout", "check_out",
    "completed", "complete", "finish", "finished", "closed", "resolved",
    "end",
    # last modification, then reversals (always latest)
    "updated", "modified", "returned", "refunded", "cancelled", "canceled",
    "deleted", "archived",
)


# Chain steps that happen within ONE sitting (a trip, a session, a surge
# window) — consecutive gaps here are minutes-to-hours, never weeks.
_EVENT_SCALE_TOKENS = ("request", "pickup", "dropoff", "departure", "arrival",
                       "begin", "board", "checkin", "checkout")

_DURATION_UNIT_NS = {
    "second": 1e9, "sec": 1e9,
    "minute": 60e9, "min": 60e9,
    "hour": 3600e9, "hr": 3600e9,
    "day": 86400e9,
}

# (start, end) column-token pairs a duration column describes, most specific
# first. trip_duration_minutes reconciles pickup→dropoff, not request→dropoff.
_DURATION_SPAN_PAIRS = (
    ("pickup", "dropoff"), ("departure", "arrival"),
    ("start", "end"), ("begin", "end"), ("checkin", "checkout"),
)


def _is_event_scale_col(col: str) -> bool:
    c = col.lower()
    if any(t in c for t in _EVENT_SCALE_TOKENS):
        return True
    # start_time/end_time (a session, a surge window) is event scale;
    # start_date/end_date (a lease, an employment) is not.
    return ("start" in c or "end" in c) and ("time" in c or c.endswith("_at"))


def _find_duration_column(df: pd.DataFrame):
    """(column, ns_per_unit) for a `*duration*` column, or (None, None)."""
    for col in df.columns:
        c = col.lower()
        if "duration" not in c:
            continue
        if df[col].dtype.kind not in "iuf":
            continue
        unit_ns = 60e9  # bare "duration" defaults to minutes
        for unit, ns in _DURATION_UNIT_NS.items():
            if unit in c.replace("duration", ""):
                unit_ns = ns
                break
        return col, unit_ns
    return None, None


def _fix_time_chains(df: pd.DataFrame, columns: set, rng: np.random.Generator) -> None:
    """Order event-sequence timestamps per row AND keep the gaps plausible.

    Three passes: (1) per-row sort so impossible orderings (dropoff before
    pickup) vanish while marginals survive; (2) gap compression — consecutive
    event-scale steps (request→pickup→dropoff) months apart collapse to a
    lognormal minutes-scale delta; (3) duration reconciliation — when the
    table declares `*_duration_minutes`, the matching span pair is rebuilt
    so end = start + duration exactly.
    """
    def _rank(col: str) -> int:
        c = col.lower()
        for i, tok in enumerate(_TIME_CHAIN_ORDER):
            if tok in c:
                return i
        return -1

    chain = [(c, _rank(c)) for c in df.columns
             if _rank(c) >= 0 and ("time" in c.lower() or "date" in c.lower() or c.lower().endswith("_at"))]
    chain = [c for c, _ in sorted(chain, key=lambda x: x[1])]
    if len(chain) < 2:
        return
    try:
        vals = df[chain].apply(pd.to_datetime, errors="coerce")
    except Exception:
        return
    if vals.isna().all().any():
        return
    ordered = np.sort(vals.values.astype("datetime64[ns]"), axis=1)
    ns = ordered.astype("int64")  # (n_rows, n_chain) epoch nanoseconds
    valid = ~np.isnan(vals.values.astype("datetime64[ns]")).any(axis=1)

    # ── Pass 2: compress implausible gaps between event-scale steps.
    # Shifting column j AND everything after it preserves all later gaps.
    _CAP_NS = int(3 * 3600e9)
    for j in range(1, len(chain)):
        if not (_is_event_scale_col(chain[j - 1]) and _is_event_scale_col(chain[j])):
            continue
        gap = ns[:, j] - ns[:, j - 1]
        too_big = valid & (gap > _CAP_NS)
        if too_big.any():
            new_gap = (rng.lognormal(np.log(15 * 60), 0.9, size=int(too_big.sum()))
                       * 1e9).astype("int64")
            np.minimum(new_gap, _CAP_NS, out=new_gap)
            shift = gap[too_big] - new_gap
            ns[np.ix_(too_big, range(j, len(chain)))] -= shift[:, None]

    # ── Pass 3: a declared duration column is the truth for its span pair.
    dur_col, unit_ns = _find_duration_column(df)
    if dur_col is not None:
        span = next(
            ((s, e) for s, e in _DURATION_SPAN_PAIRS
             if any(s in c.lower() for c in chain) and any(e in c.lower() for c in chain)),
            None,
        )
        if span is not None:
            i0 = next(i for i, c in enumerate(chain) if span[0] in c.lower())
            i1 = next(i for i, c in enumerate(chain) if span[1] in c.lower())
            if i0 < i1:
                dur = pd.to_numeric(df[dur_col], errors="coerce").values
                ok = valid & ~np.isnan(dur) & (dur > 0)
                if ok.any():
                    target = ns[ok, i0] + (dur[ok] * unit_ns).astype("int64")
                    delta = target - ns[ok, i1]
                    ns[np.ix_(ok, range(i1, len(chain)))] += delta[:, None]

    ordered = ns.astype("datetime64[ns]")
    for i, col in enumerate(chain):
        out = pd.Series(ordered[:, i]).where(pd.Series(valid), vals[col])
        df[col] = out.dt.strftime("%Y-%m-%d %H:%M:%S") if _is_text_dtype(df[col]) else out.values


def _fix_city_country(df: pd.DataFrame, columns: set, rng: np.random.Generator) -> None:
    """Re-map city values so each row's city belongs to its country.

    Fires when a table carries both a city-ish and a country-ish column and
    at least one row's pair is incoherent. Cities are resampled from the
    row's country pool; unknown countries keep their original city.
    """
    city_col = next(
        (c for c in df.columns
         if c.lower() == "city" or c.lower().endswith("_city")),
        None,
    )
    country_col = next(
        (c for c in df.columns
         if c.lower() == "country" or c.lower().endswith("_country")),
        None,
    )
    if city_col is None or country_col is None:
        return
    countries = df[country_col].astype(str)
    known_mask = countries.isin(COUNTRY_CITIES.keys())
    if not known_mask.any():
        return
    # Only rewrite rows whose current pair is incoherent.
    incoherent = known_mask & ~df.apply(
        lambda r: str(r[city_col]) in COUNTRY_CITIES.get(str(r[country_col]), ()),
        axis=1,
    )
    if not incoherent.any():
        return
    df.loc[incoherent, city_col] = [
        rng.choice(COUNTRY_CITIES[str(c)])
        for c in countries[incoherent]
    ]


_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"  # postal-safe (no I/O/Q)


def _postal_for(cc: str, prefix: str, rng: np.random.Generator) -> str:
    """Build a postal code in the national format for country code ``cc``,
    starting from the city ``prefix`` recorded in CITY_GEODATA."""
    d = lambda n: "".join(str(rng.integers(0, 10)) for _ in range(n))  # noqa: E731
    L = lambda n: "".join(rng.choice(list(_LETTERS)) for _ in range(n))  # noqa: E731
    # Numeric run of exactly n chars, keeping the city prefix at the front.
    num = lambda n: (str(prefix) + d(n))[:n]  # noqa: E731
    if cc == "CA":                       # A9A 9A9
        p = (str(prefix) + L(1))[:1]
        return f"{p}{d(1)}{L(1)} {d(1)}{L(1)}{d(1)}"
    if cc == "GB":                       # EC1 2AB (prefix already 1-2 letters)
        return f"{prefix}{d(1)} {d(1)}{L(2)}"
    if cc == "JP":                       # 100-0001
        return f"{num(3)}-{d(4)}"
    if cc == "NL":                       # 1012 AB
        return f"{num(4)} {L(2)}"
    if cc == "BR":                       # 01310-100
        return f"{num(5)}-{d(3)}"
    if cc in ("IN", "SG"):               # 6 digits
        return num(6)
    if cc == "AU":                       # 4 digits
        return num(4)
    # US, DE, FR, KR, MX, AE and default: 5-digit numeric
    return num(5)


def _city_geo_lookup():
    """Map lowercased city name -> (country_code, postal_prefix)."""
    from misata.vocab_seeds import CITY_GEODATA
    return {str(r[0]).lower(): (r[4], r[3]) for r in CITY_GEODATA}


# Fallback country-name -> (country_code, representative prefix) so a row with
# a country but an unknown city still gets a correctly-formatted postal code.
_COUNTRY_TO_CC = {
    "United States": ("US", "1"), "Canada": ("CA", "K"),
    "United Kingdom": ("GB", "B"), "Germany": ("DE", "1"),
    "France": ("FR", "7"), "India": ("IN", "1"), "Japan": ("JP", "1"),
    "Netherlands": ("NL", "1"), "Australia": ("AU", "2"), "Brazil": ("BR", "0"),
    "Mexico": ("MX", "0"), "South Korea": ("KR", "0"), "Singapore": ("SG", "0"),
    "United Arab Emirates": ("AE", "0"),
}


def _fix_postal_from_city(df: pd.DataFrame, columns: set, rng: np.random.Generator) -> None:
    """Regenerate postal codes so they match the row's city (preferred) or
    country, in the correct national format. A US-style five-digit ZIP on a
    Tokyo row is an instant tell; this ties the code to real geography.
    """
    postal_col = next(
        (c for c in df.columns if c.lower() in
         ("zip", "zip_code", "zipcode", "postal", "postal_code", "postcode")),
        None,
    )
    if postal_col is None:
        return
    city_col = next((c for c in df.columns
                     if c.lower() == "city" or c.lower().endswith("_city")), None)
    country_col = next((c for c in df.columns
                        if c.lower() == "country" or c.lower().endswith("_country")), None)
    if city_col is None and country_col is None:
        return

    geo = _city_geo_lookup()
    out = []
    for _, row in df.iterrows():
        cc_prefix = None
        if city_col is not None:
            cc_prefix = geo.get(str(row[city_col]).lower())
        if cc_prefix is None and country_col is not None:
            cc_prefix = _COUNTRY_TO_CC.get(str(row[country_col]))
        if cc_prefix is None:
            out.append(row[postal_col])          # unknown geography: leave as-is
        else:
            cc, prefix = cc_prefix
            out.append(_postal_for(cc, prefix, rng))
    df[postal_col] = out


# National phone templates: '#' is a random digit, the calling code is fixed.
_PHONE_TEMPLATES = {
    "United States": "+1 (###) ###-####", "Canada": "+1 (###) ###-####",
    "United Kingdom": "+44 #### ######", "Germany": "+49 ### #######",
    "France": "+33 # ## ## ## ##", "India": "+91 ##### #####",
    "Japan": "+81 ## #### ####", "Netherlands": "+31 # ########",
    "Australia": "+61 # #### ####", "Brazil": "+55 ## #####-####",
    "Mexico": "+52 ## #### ####", "South Korea": "+82 ## #### ####",
    "Singapore": "+65 #### ####", "United Arab Emirates": "+971 ## ### ####",
}


def _fix_phone_country(df: pd.DataFrame, columns: set, rng: np.random.Generator) -> None:
    """Re-map phone numbers so each row's number uses its country's calling
    code and format. A +1 US number on a Tokyo row is an obvious tell."""
    phone_col = next(
        (c for c in df.columns
         if "phone" in c.lower() or "mobile" in c.lower()
         or {"tel", "telephone"} & set(c.lower().split("_"))),
        None,
    )
    country_col = next((c for c in df.columns
                        if c.lower() == "country" or c.lower().endswith("_country")), None)
    if phone_col is None or country_col is None:
        return
    countries = df[country_col].astype(str)
    if not countries.isin(_PHONE_TEMPLATES).any():
        return
    out = []
    for orig, country in zip(df[phone_col], countries):
        tmpl = _PHONE_TEMPLATES.get(str(country))
        if tmpl is None:
            out.append(orig)
        else:
            out.append("".join(str(rng.integers(0, 10)) if ch == "#" else ch
                               for ch in tmpl))
    df[phone_col] = out


def _fix_state_country(df: pd.DataFrame, columns: set, rng: np.random.Generator) -> None:
    """Re-map state/province values so each row's state belongs to its country.

    Without this an address reads "Curitiba, Indiana, Brazil" — a US state in
    a Brazilian row. Fires when the table carries both a state-ish and a
    country-ish column; states are resampled from the row's country pool.
    """
    state_col = next(
        (c for c in df.columns
         if c.lower() in ("state", "province", "region", "state_province")
         or c.lower().endswith("_state") or c.lower().endswith("_province")),
        None,
    )
    country_col = next(
        (c for c in df.columns
         if c.lower() == "country" or c.lower().endswith("_country")),
        None,
    )
    if state_col is None or country_col is None:
        return
    countries = df[country_col].astype(str)
    known_mask = countries.isin(COUNTRY_STATES.keys())
    if not known_mask.any():
        return

    # When the row's city is a known one, its actual state is the truth:
    # São Paulo city gets São Paulo state, not a random Brazilian province.
    from misata.vocab_seeds import CITY_STATE
    city_col = next(
        (c for c in df.columns
         if c.lower() == "city" or c.lower().endswith("_city")),
        None,
    )
    if city_col is not None:
        exact = df[city_col].astype(str).map(CITY_STATE)
        has_exact = exact.notna()
        if has_exact.any():
            df.loc[has_exact, state_col] = exact[has_exact]

    incoherent = known_mask & ~df.apply(
        lambda r: str(r[state_col]) in COUNTRY_STATES.get(str(r[country_col]), ()),
        axis=1,
    )
    if not incoherent.any():
        return
    df.loc[incoherent, state_col] = [
        rng.choice(COUNTRY_STATES[str(c)])
        for c in countries[incoherent]
    ]


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

    # ── Geographic coherence: a row's city must belong to its country ──
    # (column generation order means the city may have been sampled before
    # the country existed; this pass runs after the full table is built).
    _fix_city_country(df, columns, _rng)
    _fix_state_country(df, columns, _rng)
    _fix_postal_from_city(df, columns, _rng)
    _fix_phone_country(df, columns, _rng)
    _fix_time_chains(df, columns, _rng)

    # ── Temporal consistency ──
    _fix_created_updated(df, columns, _rng)
    _fix_start_end_dates(df, columns, _rng)
    _fix_created_delivered(df, columns, _rng)
    _fix_delivered_requires_status(df, columns)
    _fix_age_from_dob(df, columns)

    # ── Monetary consistency ──
    _fix_cost_less_than_price(df, columns, _rng)
    _fix_discount_cap(df, columns)
    _fix_line_total(df, columns)
    _fix_order_total(df, columns)
    _fix_amount_from_base_and_multiplier(df, columns)
    _apply_plan_price_mapping(df, columns)
    _fix_rankable_lookup_monotonicity(df, columns, table_name)

    # ── Identity consistency ──
    _fix_gender_name_coherence(df, columns, _rng)   # before email: email derives from the fixed name
    _fix_email_from_name(df, columns, _rng)
    _fix_corporate_email(df, columns, _rng)
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
    """A ship/deliver timestamp must not exist unless the row's status has
    reached that stage. A cancelled or pending order with a shipped_date is
    the kind of contradiction a developer spots instantly in seed data.

    Matches any column whose name contains 'deliver' or 'ship' (delivered_at,
    delivery_date, shipped_date, ship_date, ...) against the row's status.
    """
    # 'state' is deliberately excluded: it is far more often a US-state column
    # than an order-state one, and a mis-gate there is highly visible.
    status_col = next((c for c in df.columns
                       if c.lower() in ("status", "order_status", "fulfillment_status")),
                      None)
    if status_col is None:
        return
    status = df[status_col].astype(str).str.strip().str.lower()
    for col in df.columns:
        lc = col.lower()
        is_time = "time" in lc or "date" in lc or lc.endswith("_at")
        is_tracking = ("tracking" in lc or "awb" in lc or "waybill" in lc
                       or "shipment_number" in lc)
        if not (is_time or is_tracking):
            continue
        if is_tracking:
            allowed = SHIPPED_STATUSES
        elif "deliver" in lc:
            allowed = DELIVERED_STATUSES
        elif "ship" in lc or "dispatch" in lc:
            allowed = SHIPPED_STATUSES
        else:
            continue
        # Only enforce when the status vocabulary actually overlaps the gate,
        # so we never blank a column whose statuses we don't recognise.
        if not (set(status.unique()) & allowed):
            continue
        not_reached = ~status.isin(allowed)
        if not_reached.any():
            df.loc[not_reached, col] = None


def _fix_age_from_dob(df: pd.DataFrame, columns: set[str]) -> None:
    """An ``age`` column must agree with ``date_of_birth`` (or birth_date/dob).

    Age is derived from the birth date as of the dataset's latest known moment
    (the max of any other datetime column), falling back to a fixed reference
    so the result stays reproducible for a birthdate-only table.
    """
    age_col = next((c for c in columns if c.lower() in ("age", "age_years")), None)
    dob_col = next((c for c in columns if c.lower() in
                    ("date_of_birth", "birth_date", "birthdate", "dob", "born_on")),
                   None)
    if age_col is None or dob_col is None:
        return
    dob = pd.to_datetime(df[dob_col], errors="coerce")
    if dob.isna().all():
        return

    # "Now" = the latest timestamp the dataset references, else the fixed ref.
    ref = pd.Timestamp(_AGE_REFERENCE)
    for c in df.columns:
        if c == dob_col:
            continue
        if "date" in c.lower() or "time" in c.lower() or c.lower().endswith("_at"):
            other = pd.to_datetime(df[c], errors="coerce")
            if other.notna().any():
                ref = max(ref, other.max())
    years = ((ref - dob).dt.days / 365.25).round().astype("Int64")
    years = years.clip(lower=0, upper=120)
    df[age_col] = years


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
        discount = (pd.to_numeric(df["discount"], errors="coerce").fillna(0)
                    if "discount" in columns else 0)
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


def _fix_amount_from_base_and_multiplier(df: pd.DataFrame, columns: set[str]) -> None:
    """Derived money math: fare_amount = base_fare × surge_multiplier.

    Fires when a table carries base_<stem>, a *_multiplier column, and a
    <stem>_amount / <stem>_total / total_<stem> / <stem> target. The target
    is recomputed so the arithmetic audits clean; an independently sampled
    fare next to its own factors is the fastest tell in generated data.
    """
    lower = {c.lower(): c for c in df.columns}
    mult_col = next(
        (lower[c] for c in lower if c.endswith("_multiplier") or c == "multiplier"),
        None,
    )
    if mult_col is None:
        return
    for c in list(lower):
        if not c.startswith("base_"):
            continue
        stem = c[5:]
        target = next(
            (lower[t] for t in (f"{stem}_amount", f"{stem}_total",
                                f"total_{stem}", stem) if t in lower),
            None,
        )
        if target is None or target == mult_col:
            continue
        base = pd.to_numeric(df[lower[c]], errors="coerce")
        mult = pd.to_numeric(df[mult_col], errors="coerce")
        ok = base.notna() & mult.notna()
        if not ok.any():
            continue
        df.loc[ok, target] = np.round(base[ok] * mult[ok], 2)


# Rank families for lookup-table labels. Within a family, position = rank;
# a tier table's numeric columns (fees, limits, credits) must ascend with it.
_RANK_FAMILIES = [
    ["bronze", "silver", "gold", "platinum", "diamond", "elite"],
    # the membership REFERENCE_TIER_POOL mixes a plan word into the metals
    ["free", "basic", "bronze", "silver", "gold", "platinum", "diamond", "elite"],
    ["free", "trial", "lite", "basic", "starter", "standard", "plus",
     "growth", "pro", "premium", "advanced", "business", "scale",
     "enterprise", "ultimate"],
    ["extra small", "small", "medium", "large", "extra large"],
    ["micro", "small", "medium", "large", "enterprise"],
    ["very low", "low", "moderate", "medium", "high", "very high"],
    ["junior", "mid-level", "senior", "staff", "principal"],
    ["economy", "comfort", "premium", "luxury"],
    ["student", "individual", "family", "corporate", "lifetime"],
]

_RANK_LABEL_COLS = ("tier", "level", "plan", "grade", "rank", "band",
                    "name", "label", "membership", "class", "size", "segment")

_RANKABLE_TABLE_RE = re.compile(
    r"(tiers?|levels?|plans?|grades?|ranks?|bands?|brackets?|memberships?|sizes?)$",
    re.IGNORECASE,
)


def _fix_rankable_lookup_monotonicity(df: pd.DataFrame, columns: set[str], table_name: str = "") -> None:
    """Numeric columns of a rankable lookup table ascend with the tier rank.

    A membership_tiers table where Silver costs 130 and Platinum costs 96 is
    instantly fake. The fix keeps the generated VALUES (spec-shaped) and
    reassigns them so rank order and numeric order agree.
    """
    if len(df) > 50 or len(df) < 2:
        return
    if not _RANKABLE_TABLE_RE.search(str(table_name or "")):
        return
    label_col = next(
        (c for c in df.columns
         if c.lower() in _RANK_LABEL_COLS and _is_text_dtype(df[c])),
        None,
    )
    if label_col is None:
        return
    labels = df[label_col].astype(str).str.strip().str.lower()
    ranks = None
    for family in _RANK_FAMILIES:
        pos = {name: i for i, name in enumerate(family)}
        cand = labels.map(pos)
        if cand.notna().all() and cand.nunique() == len(df):
            ranks = cand.astype(int)
            break
    if ranks is None:
        return
    order = np.argsort(ranks.values)  # row indices from lowest to highest tier
    for col in df.columns:
        if col == label_col or col.lower() == "id" or col.lower().endswith("_id"):
            continue
        if df[col].dtype.kind == "b" or _is_text_dtype(df[col]):
            continue
        vals = pd.to_numeric(df[col], errors="coerce")
        if vals.isna().any() or vals.nunique() <= 1:
            continue
        sorted_vals = np.sort(vals.values)
        out = np.empty(len(df), dtype=float)
        out[order] = sorted_vals
        df[col] = out.astype(df[col].dtype) if df[col].dtype.kind in "iu" else out


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


# Trailing company-type words dropped when turning a company name into a domain.
_CORP_SUFFIXES = {
    "inc", "llc", "ltd", "limited", "co", "corp", "corporation", "company",
    "group", "holdings", "partners", "ventures", "labs", "technologies",
    "technology", "tech", "solutions", "systems", "analytics", "works",
    "studio", "studios", "industries", "enterprises", "international", "global",
}


def _company_domain(company: str) -> "str | None":
    words = [w for w in re.sub(r"[^a-z0-9 ]", "", str(company).lower()).split()
             if w and w not in _CORP_SUFFIXES]
    if not words:
        return None
    return "".join(words) + ".com"


def _fix_corporate_email(df: pd.DataFrame, columns: set[str], rng: np.random.Generator) -> None:
    """A work/corporate email must use the company's domain, not a free
    webmail provider. "Vijay Becker at Blue Peak Labs" with vbecker@outlook.com
    is wrong; it should be vbecker@bluepeak.com.
    """
    email_col = next((c for c in df.columns if c.lower() in
                      ("work_email", "corporate_email", "company_email",
                       "business_email", "office_email")), None)
    company_col = next((c for c in df.columns if c.lower() in
                        ("company", "company_name", "employer", "organization",
                         "organisation", "org_name", "account_name")), None)
    if email_col is None or company_col is None:
        return

    def _clean(part: str) -> str:
        return re.sub(r"[^a-z]", "", str(part).lower().strip())

    if {"first_name", "last_name"}.issubset(columns):
        firsts, lasts = df["first_name"].astype(str), df["last_name"].astype(str)
    elif "name" in columns:
        parts = df["name"].astype(str).str.strip().str.split()
        firsts, lasts = parts.str[0], parts.str[-1]
    else:
        firsts = lasts = None

    out = []
    seps = rng.choice([".", "_", ""], size=len(df), p=[0.7, 0.15, 0.15])
    for i in range(len(df)):
        domain = _company_domain(df.iloc[i][company_col])
        if domain is None:
            out.append(df.iloc[i][email_col])
            continue
        if firsts is not None:
            f, l = _clean(firsts.iloc[i]), _clean(lasts.iloc[i])
            local = f"{f}{seps[i]}{l}".strip(".") or "contact"
        else:
            local = "contact"
        out.append(f"{local}@{domain}")
    df[email_col] = out


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
    if "category" not in columns:
        return
    # The product-name column is usually "name", but marketplace/catalog tables
    # call it "title" (and occasionally "product_name"). Pick whichever exists.
    name_col = next((c for c in ("name", "title", "product_name") if c in columns), None)
    if name_col is None:
        return
    tl = table_name.lower()
    _PRODUCT_TABLE_TOKENS = (
        "product", "item", "listing", "catalog", "catalogue", "marketplace",
        "sku", "merchandise", "inventory", "offer", "goods",
    )
    if not any(tok in tl for tok in _PRODUCT_TABLE_TOKENS):
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

    # Map a category VALUE present in the table back to a canonical product pool,
    # so we can drive names from the (usually diverse) category enum.
    def _cat_to_pool(cat_value: str) -> Optional[str]:
        cl = str(cat_value).lower()
        for p in PRODUCT_NAME_POOLS:
            if p in cl or cl in p or p in cl.split():
                return p
        return None

    # Decide the authoritative direction. The product-name column frequently
    # collapses to a single default pool (it is generated before the category
    # column is available), whereas the category enum is a proper, diverse draw.
    # When the category column is the more diverse signal AND it maps cleanly to
    # product pools, drive NAMES from CATEGORY (preserves diversity + coherence).
    # Otherwise fall back to the original name→category direction.
    names = df[name_col].tolist()
    cats = df["category"].tolist()
    name_pools = {_NAME_TO_POOL.get(str(n)) for n in names} - {None}
    cat_pools = {_cat_to_pool(c) for c in cats} - {None}
    category_authoritative = len(cat_pools) > len(name_pools) and len(cat_pools) >= 2

    if category_authoritative:
        for i, cat in enumerate(cats):
            pool = _cat_to_pool(cat)
            if pool is None:
                continue
            cur_pool = _NAME_TO_POOL.get(str(names[i]))
            if cur_pool != pool:  # name doesn't belong to its category — regenerate it
                pool_names = PRODUCT_NAME_POOLS[pool]
                names[i] = pool_names[hash(str(names[i]) + str(i)) % len(pool_names)]
    else:
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
                # Name's pool (e.g. "food") has no category in this store. Swap the NAME to a
                # product from a representable pool, deterministically chosen from the row's
                # current category so the (name, category) pair is coherent.
                cur = str(cats[i]).lower()
                target_pool = next(
                    (p for p in representable
                     if p in cur or cur in p or p in cur.split()),
                    sorted(representable)[0],
                )
                pool_names = PRODUCT_NAME_POOLS[target_pool]
                names[i] = pool_names[hash(nm) % len(pool_names)]
    df[name_col] = names
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
