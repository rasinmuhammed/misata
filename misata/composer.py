"""
Compositional schema synthesis: structural schemas for domains Misata has
never seen — without an LLM and without making things up.

The keyword→template path fails two ways on an unknown story: it either
confabulates (matching "clinic" and dealing out human psychiatrists for a
veterinary practice) or collapses to one generic table. This module is the
honest third way, built on a distinction that holds up:

    STRUCTURE is derivable from the sentence.   SEMANTICS are not.

"A drone delivery startup tracking flights, battery swaps, and delivery
zones" mechanically yields entities (plural noun phrases), row counts
("200 patients" binds a count), and — via a small archetype lattice —
structure: *people* have names and emails, *assets* have models and
maintenance states, *places* have geography, *events* have timestamps,
statuses and foreign keys to the actors involved, *documents* have authors
and free text. None of that pretends to know what a drone is.

What this module will NOT do is invent domain semantics: no fabricated
column meanings, no guessed vocabularies. Unknown entities get honest
structural columns (reference codes, statuses, timestamps). The detection
report says exactly that, and points to the two upgrade paths: a schema
dict, or an LLM (BYO key / MCP caller) for domain-specific columns.

Composed columns deliberately reuse Misata's realism core: person columns
flow through joint name sampling, timestamps through temporal profiles,
statuses through Zipfian categoricals, free text through the microtext
grammar. Structure from the sentence, realism from the engine.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from misata.schema import Column, Relationship, SchemaConfig, Table

# ---------------------------------------------------------------------------
# Lexicons — archetype membership for common business-English entity heads.
# A lexicon hit beats morphology; morphology beats nothing; the fallback is
# an honest "record" archetype, never a guess.
# ---------------------------------------------------------------------------

PERSON_WORDS = {
    "user", "customer", "employee", "patient", "doctor", "nurse", "driver",
    "owner", "member", "student", "teacher", "instructor", "agent", "client",
    "technician", "rider", "courier", "host", "guest", "player", "subscriber",
    "contractor", "volunteer", "donor", "tenant", "landlord", "passenger",
    "attendee", "applicant", "recruiter", "manager", "freelancer", "vendor",
    "supplier", "operator", "engineer", "developer", "designer", "analyst",
    "consultant", "therapist", "trainer", "coach", "pilot", "mechanic",
    "farmer", "worker", "staff", "resident", "visitor", "buyer", "seller",
    "author", "artist", "musician", "speaker", "mentor", "mentee", "patron",
}

ASSET_WORDS = {
    "drone", "vehicle", "truck", "car", "van", "machine", "device", "product",
    "item", "robot", "sensor", "server", "tool", "asset", "battery",
    "aircraft", "ship", "container", "printer", "turbine", "panel",
    "instrument", "scooter", "bike", "bicycle", "camera", "laptop", "phone",
    "tablet", "appliance", "generator", "pump", "valve", "motor", "engine",
    "trailer", "forklift", "crane", "tractor", "satellite", "antenna",
    "router", "terminal", "kiosk", "meter", "charger", "lock", "monitor",
    "animal", "horse", "cow", "dog", "cat", "plant", "tree", "crop",
}

PLACE_WORDS = {
    "zone", "warehouse", "site", "region", "location", "hub", "store",
    "branch", "facility", "depot", "station", "office", "plant", "port",
    "campus", "venue", "district", "area", "lot", "yard", "field", "farm",
    "kitchen", "garage", "dock", "floor", "room", "building", "outlet",
    "stand", "market", "garden", "greenhouse", "lab", "laboratory",
}

EVENT_WORDS = {
    "order", "payment", "transaction", "delivery", "flight", "trip", "visit",
    "appointment", "swap", "repair", "inspection", "booking", "session",
    "shipment", "ride", "claim", "donation", "rental", "sale", "purchase",
    "return", "exchange", "transfer", "deposit", "withdrawal", "login",
    "signup", "click", "view", "match", "lesson", "consultation", "surgery",
    "treatment", "test", "scan", "audit", "incident", "outage", "alert",
    "checkup", "pickup", "dropoff", "stop", "call", "meeting", "interview",
    "enrollment", "reservation", "checkout", "refund", "renewal", "upgrade",
    "installation", "calibration", "harvest", "batch", "run", "job", "task",
    "shift", "race", "tournament", "workout", "class", "walk", "vaccination",
}

DOCUMENT_WORDS = {
    "note", "report", "log", "ticket", "review", "record", "invoice",
    "receipt", "contract", "certificate", "prescription", "message", "post",
    "comment", "article", "entry", "form", "survey", "complaint", "quote",
    "estimate", "proposal", "memo", "manifest", "statement", "summary",
}

# Events that plausibly carry a monetary amount.
MONETARY_EVENTS = {
    "order", "payment", "transaction", "sale", "purchase", "donation",
    "rental", "deposit", "withdrawal", "transfer", "refund", "claim",
    "booking", "invoice", "checkout", "renewal",
}

# Words that are never entities: the organisation itself, metrics, units.
NON_ENTITY_WORDS = {
    # organisation / story scaffolding
    "startup", "company", "business", "platform", "system", "app", "service",
    "agency", "firm", "team", "organization", "organisation", "enterprise",
    "shop", "clinic", "hospital", "practice", "studio", "brand", "chain",
    # metrics & abstractions (these become curves/columns, not tables)
    "revenue", "sales", "growth", "churn", "rate", "rates", "fee", "fees",
    "cost", "costs", "profit", "margin", "percent", "percentage", "average",
    "total", "volume", "capacity", "price", "prices", "amount", "amounts",
    # time units
    "year", "years", "month", "months", "week", "weeks", "day", "days",
    "hour", "hours", "minute", "minutes", "quarter", "quarters",
    # currencies / quantities
    "dollar", "dollars", "euro", "euros", "unit", "units", "piece", "pieces",
}

# Common verbs ending in -s that a plural detector would misread.
VERB_S_BLACKLIST = {
    "tracks", "manages", "includes", "handles", "has", "contains", "sells",
    "ships", "runs", "monitors", "records", "stores", "supports", "serves",
    "offers", "provides", "needs", "wants", "uses", "creates", "generates",
    "processes", "is", "was", "does", "gets", "makes", "takes", "gives",
    "operates", "delivers", "schedules", "assigns", "owns", "rents",
}

STOPWORDS = {
    "a", "an", "the", "and", "or", "with", "of", "for", "to", "in", "on",
    "at", "by", "from", "per", "each", "every", "their", "its", "our",
    "that", "this", "these", "those", "across", "around", "about", "plus",
    "via", "through", "using", "into", "onto", "over", "under", "between",
    "during", "without", "within", "against", "towards", "among",
    "tracking", "managing", "including", "handling", "covering", "running",
    "selling", "serving", "offering", "providing", "monitoring", "logging",
    "new", "active", "monthly", "daily", "weekly", "annual", "recurring",
    "small", "large", "big", "local", "global", "online", "digital",
}

IRREGULAR_PLURALS = {
    "people": "person", "children": "child", "men": "man", "women": "woman",
    "mice": "mouse", "geese": "goose", "feet": "foot", "teeth": "tooth",
    "staff": "staff", "sheep": "sheep", "cattle": "cattle", "oxen": "ox",
}

_NUMBER_ENTITY = re.compile(
    r"(\d[\d,]*(?:\.\d+)?)\s*(k|m)?\s+([a-z][a-z-]*(?:\s+[a-z][a-z-]*)?)", re.I
)


def singularize(word: str) -> str:
    word = word.lower()
    if word in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[word]
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    # -es stripping only where the stem demands it: classes/boxes/churches.
    # Plain -ses with a vowel stem (horses, nurses, purchases) just drops -s.
    if word.endswith(("sses", "xes", "zes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _is_plural_noun(token: str) -> bool:
    if token in VERB_S_BLACKLIST or token in STOPWORDS or token in NON_ENTITY_WORDS:
        return False
    if token in IRREGULAR_PLURALS:
        return True
    if len(token) < 3 or not token.isalpha():
        return False
    if not token.endswith("s") or token.endswith(("ss", "us", "is")):
        return False
    return singularize(token) not in NON_ENTITY_WORDS


def archetype_of(singular_head: str) -> str:
    """Lexicon first, morphology second, honest 'record' fallback last."""
    if singular_head in PERSON_WORDS:
        return "person"
    if singular_head in ASSET_WORDS:
        return "asset"
    if singular_head in PLACE_WORDS:
        return "place"
    if singular_head in EVENT_WORDS:
        return "event"
    if singular_head in DOCUMENT_WORDS:
        return "document"
    # Deverbal suffixes mark processes/events (inspection, shipment, crossing)
    if singular_head.endswith(("tion", "sion", "ment", "ance", "ence", "ing")):
        return "event"
    # Safe agentive suffixes mark people (chemist, librarian, attendee,
    # beekeeper). Bare -er/-or is NOT safe (printer, sensor) and is left to
    # the lexicons above.
    if singular_head.endswith(("ist", "ian", "ee", "eer", "keeper", "smith")):
        return "person"
    return "record"


@dataclass
class ComposedEntity:
    phrase: str            # "battery swap"
    table_name: str        # "battery_swaps"
    singular: str          # "battery_swap" (snake, used for PK naming)
    archetype: str
    row_count: Optional[int] = None
    monetary: bool = False


def _pluralize_snake(singular_snake: str) -> str:
    head = singular_snake.rsplit("_", 1)[-1]
    if head.endswith("y") and head[-2] not in "aeiou":
        plural_head = head[:-1] + "ies"
    elif head.endswith(("s", "x", "z", "ch", "sh")):
        plural_head = head + "es"
    else:
        plural_head = head + "s"
    return singular_snake[: len(singular_snake) - len(head)] + plural_head


def extract_entities(story: str) -> List[ComposedEntity]:
    """Plural noun phrases → entities; '200 patients' binds row counts."""
    text = re.sub(r"[^a-z0-9\s,;.-]", " ", story.lower())
    text = re.sub(r"[,;.]", " , ", text)
    tokens = text.split()

    entities: Dict[str, ComposedEntity] = {}

    def _add(phrase_tokens: List[str]) -> Optional[ComposedEntity]:
        head_singular = singularize(phrase_tokens[-1])
        singular_snake = "_".join(phrase_tokens[:-1] + [head_singular])
        if singular_snake in entities:
            return entities[singular_snake]
        arche = archetype_of(head_singular)
        entity = ComposedEntity(
            phrase=" ".join(phrase_tokens),
            table_name=_pluralize_snake(singular_snake),
            singular=singular_snake,
            archetype=arche,
            monetary=head_singular in MONETARY_EVENTS,
        )
        entities[singular_snake] = entity
        return entity

    for i, token in enumerate(tokens):
        if not _is_plural_noun(token):
            continue
        phrase = [token]
        # one noun-ish modifier may precede: "battery swaps", "treatment notes"
        if i > 0:
            prev = tokens[i - 1]
            if (
                prev.isalpha()
                and prev not in STOPWORDS
                and prev not in NON_ENTITY_WORDS
                and prev not in VERB_S_BLACKLIST
                and prev != ","
                and not _is_plural_noun(prev)
                and not prev.isdigit()
            ):
                phrase = [singularize(prev) if prev.endswith("s") else prev, token]
        _add(phrase)

    # Known asset words appearing only as singular modifiers ("drone delivery
    # startup") still earn a table — events will reference them.
    for token in tokens:
        if token in ASSET_WORDS and singularize(token) not in entities:
            _add([token])

    # Bind explicit counts: "200 patients", "50 battery swaps", "5k users"
    for match in _NUMBER_ENTITY.finditer(story.lower()):
        number, suffix, words = match.groups()
        count = float(number.replace(",", ""))
        if suffix == "k":
            count *= 1_000
        elif suffix == "m":
            count *= 1_000_000
        for n_words in (2, 1):
            phrase_tokens = words.split()[:n_words]
            if not phrase_tokens:
                continue
            head_singular = singularize(phrase_tokens[-1])
            key = "_".join(phrase_tokens[:-1] + [head_singular])
            if key in entities:
                entities[key].row_count = int(count)
                break
            if head_singular in entities and n_words == 1:
                entities[head_singular].row_count = int(count)
                break

    # Persons/assets/places first (parents), then events, then documents.
    order = {"person": 0, "asset": 1, "place": 2, "record": 3, "event": 4, "document": 5}
    result = sorted(entities.values(), key=lambda e: order[e.archetype])
    return result[:6]


# ---------------------------------------------------------------------------
# Column synthesis per archetype
# ---------------------------------------------------------------------------

_DATE_RANGE = {"start": "2022-01-01", "end": "2024-12-31"}


def _default_rows(entity: ComposedEntity, base: int) -> int:
    if entity.row_count:
        return entity.row_count
    return {
        "person": base,
        "asset": max(base // 5, 10),
        "place": max(min(base // 50, 20), 4),
        "event": base * 3,
        "document": base,
        "record": base,
    }[entity.archetype]


def _pk(entity: ComposedEntity, rows: int) -> Column:
    return Column(
        name=f"{entity.singular}_id",
        type="int",
        unique=True,
        distribution_params={"min": 1, "max": rows * 2},
    )


def _columns_for(
    entity: ComposedEntity,
    rows: int,
    parents: List[ComposedEntity],
) -> List[Column]:
    head = entity.singular.rsplit("_", 1)[-1]
    cols: List[Column] = [_pk(entity, rows)]
    cols.extend(
        Column(name=f"{p.singular}_id", type="foreign_key") for p in parents
    )

    if entity.archetype == "person":
        cols += [
            Column(name="first_name", type="text", distribution_params={"text_type": "first_name"}),
            Column(name="last_name", type="text", distribution_params={"text_type": "last_name"}),
            Column(name="email", type="text", distribution_params={"text_type": "email"}),
            Column(name="joined_at", type="date", distribution_params=dict(_DATE_RANGE)),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["active", "inactive", "pending"],
            }),
        ]
    elif entity.archetype == "asset":
        models = [f"{head.title()} {suffix}" for suffix in
                  ("A-100", "A-200", "B-300", "X1", "X2", "Pro", "Mini", "Max")]
        cols += [
            Column(name="model", type="categorical", distribution_params={"choices": models}),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["available", "in_use", "maintenance", "retired"],
            }),
            Column(name="acquired_date", type="date", distribution_params={"start": "2019-01-01", "end": "2024-06-30"}),
        ]
    elif entity.archetype == "place":
        names = [f"{direction} {head.title()}" for direction in
                 ("North", "South", "East", "West", "Central", "Harbor",
                  "Airport", "Downtown", "Riverside", "Hillside", "Lakeview", "Midtown")]
        cols += [
            Column(name="name", type="categorical", distribution_params={"choices": names}),
            Column(name="city", type="text", distribution_params={"text_type": "city"}),
            Column(name="is_active", type="boolean", distribution_params={"probability": 0.85}),
        ]
    elif entity.archetype == "event":
        cols += [
            Column(name=f"{head}_date", type="date", distribution_params=dict(_DATE_RANGE)),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["completed", "scheduled", "in_progress", "cancelled"],
            }),
        ]
        if entity.monetary:
            cols.append(Column(name="amount", type="float", distribution_params={
                "distribution": "lognormal", "mean": 120.0, "std": 80.0,
                "min": 1.0, "decimals": 2,
            }))
    elif entity.archetype == "document":
        cols += [
            Column(name="content", type="text", distribution_params={"text_type": "sentence"}),
            Column(name="created_at", type="date", distribution_params=dict(_DATE_RANGE)),
        ]
    else:  # "record": honest structure, no invented semantics
        prefix = re.sub(r"[^A-Z]", "", head.upper())[:3] or "REC"
        cols += [
            Column(name="reference_code", type="text", distribution_params={
                "pattern": prefix + r"-\d{5}",
            }),
            Column(name="status", type="categorical", distribution_params={
                "choices": ["open", "active", "closed", "archived"],
            }),
            Column(name="created_at", type="date", distribution_params=dict(_DATE_RANGE)),
            Column(name="value", type="float", distribution_params={
                "distribution": "lognormal", "mean": 100.0, "std": 60.0,
                "min": 0.0, "decimals": 2,
            }),
        ]
    return cols


def compose_schema(story: str, default_rows: int = 1000) -> Optional[SchemaConfig]:
    """Compose a structural multi-table schema from story entities.

    Returns None when the story yields no usable entities — the caller
    should fall back to its generic single-table schema (curve extraction
    still works there).
    """
    entities = extract_entities(story)
    if not entities:
        return None

    # Events reference the domain's nouns whatever their archetype: an
    # unknown noun ("hives") still anchors FK structure — that's structure,
    # not semantics. Known archetypes are preferred parents.
    archetype_rank = {"person": 0, "asset": 1, "place": 2, "record": 3}
    parents_pool = sorted(
        (e for e in entities if e.archetype in archetype_rank),
        key=lambda e: archetype_rank[e.archetype],
    )
    events = [e for e in entities if e.archetype == "event"]

    tables: List[Table] = []
    columns: Dict[str, List[Column]] = {}
    relationships: List[Relationship] = []

    for entity in entities:
        rows = _default_rows(entity, default_rows)

        if entity.archetype in ("person", "asset", "place", "record"):
            parents: List[ComposedEntity] = []
        elif entity.archetype == "event":
            # events reference the actors/assets/places involved (max 3)
            parents = parents_pool[:3]
        else:  # document: authored by a person, attached to an event
            parents = [e for e in entities if e.archetype == "person"][:1]
            parents += events[:1]

        tables.append(Table(name=entity.table_name, row_count=rows))
        columns[entity.table_name] = _columns_for(entity, rows, parents)
        relationships.extend(
            Relationship(
                parent_table=p.table_name,
                child_table=entity.table_name,
                parent_key=f"{p.singular}_id",
                child_key=f"{p.singular}_id",
            )
            for p in parents
        )

    entity_summary = ", ".join(
        f"{e.table_name} ({e.archetype})" for e in entities
    )
    return SchemaConfig(
        name="Composed Dataset",
        description=(
            f"Structurally composed from story entities: {entity_summary}. "
            "Column semantics are structural, not domain-specific."
        ),
        tables=tables,
        columns=columns,
        relationships=relationships,
        events=[],
        outcome_curves=[],
    )
