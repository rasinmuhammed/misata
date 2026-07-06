"""Wikidata capsule builder: real entity names, fetched once, CC0, auditable.

The architecture rule this module serves: NEVER fetch at generation time.
This builder runs at capsule-build time (a CLI command, a design-time studio
action), spends the network once, and emits a capsule whose every value list
carries provenance (the Wikidata class QID it came from, CC0 license, fetch
timestamp). Generation then reads the capsule offline and deterministically.

Why Wikidata over web scraping or dataset hunting for entity NAMES:
- CC0 licensed: zero legal ambiguity for shipped vocabulary.
- Structured: "instances of wristwatch model" is a query, not a scrape.
- Relational: P176 (manufacturer) turns a flat list into a conditional map
  (brand → models), which is what keeps a Rolex Submariner from becoming a
  Patek Philippe Submariner.

Everything fetched passes through the vocabulary validator before it can
enter a capsule; unlabeled entities (bare QIDs) and junk labels are rejected.

Uses stdlib urllib only — no new dependency.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import Dict, List, Optional, Tuple

from misata.domain_capsule import AssetProvenance, DomainCapsule, VocabularyAsset
from misata.vocab_validator import validate_vocabulary

SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
SEARCH_ENDPOINT = "https://www.wikidata.org/w/api.php"
# Wikimedia asks automated clients to identify themselves.
USER_AGENT = "misata-capsule-builder/1.0 (https://github.com/rasinmuhammed/misata)"

_DEFAULT_TIMEOUT = 45


def _http_json(url: str, timeout: int = _DEFAULT_TIMEOUT) -> dict:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/sparql-results+json, application/json",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_sparql(query: str, timeout: int = _DEFAULT_TIMEOUT) -> List[dict]:
    """Execute a SPARQL query, returning the raw result bindings."""
    url = SPARQL_ENDPOINT + "?" + urllib.parse.urlencode({
        "query": query, "format": "json",
    })
    data = _http_json(url, timeout=timeout)
    return data.get("results", {}).get("bindings", [])


def search_class(term: str, language: str = "en") -> Optional[Tuple[str, str]]:
    """Resolve a plain-English topic to a Wikidata entity (qid, label).

    Uses wbsearchentities; returns the top hit or None. The caller should
    surface the resolved label so a human can catch a bad match — mapping
    "watch" to the timepiece rather than the verb is exactly the kind of
    ambiguity that deserves a review step.
    """
    url = SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({
        "action": "wbsearchentities", "search": term, "language": language,
        "type": "item", "format": "json", "limit": 5,
    })
    data = _http_json(url)
    hits = data.get("search", [])
    if not hits:
        return None
    top = hits[0]
    return (top["id"], top.get("label", term))


def fetch_class_members(
    class_qid: str,
    limit: int = 300,
    language: str = "en",
) -> List[str]:
    """Labels of entities that are instances of (or subclasses under) a class."""
    query = f"""
    SELECT DISTINCT ?itemLabel WHERE {{
      ?item wdt:P31/wdt:P279* wd:{class_qid} .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
    }}
    LIMIT {int(limit)}
    """
    rows = run_sparql(query)
    return [r["itemLabel"]["value"] for r in rows if "itemLabel" in r]


def fetch_conditional_members(
    class_qid: str,
    parent_property: str,
    limit: int = 500,
    language: str = "en",
) -> Dict[str, List[str]]:
    """Class members grouped by a parent property (P176 = manufacturer).

    Returns {parent_label: [member_labels]} — the conditional map that keeps
    child values coherent with their parent (brand → models).
    """
    query = f"""
    SELECT DISTINCT ?itemLabel ?parentLabel WHERE {{
      ?item wdt:P31/wdt:P279* wd:{class_qid} .
      ?item wdt:{parent_property} ?parent .
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{language}" . }}
    }}
    LIMIT {int(limit)}
    """
    rows = run_sparql(query)
    grouped: Dict[str, List[str]] = {}
    for r in rows:
        item = r.get("itemLabel", {}).get("value")
        parent = r.get("parentLabel", {}).get("value")
        if item and parent:
            grouped.setdefault(parent, []).append(item)
    return grouped


def capsule_from_wikidata(
    domain: str,
    column: str,
    topic: Optional[str] = None,
    class_qid: Optional[str] = None,
    conditional_property: Optional[str] = None,
    parent_column: Optional[str] = None,
    limit: int = 300,
) -> DomainCapsule:
    """Build a validated, provenance-stamped capsule from Wikidata.

    Args:
        domain: capsule domain name (e.g. "vintage-watches").
        column: the schema column these values feed (e.g. "model").
        topic:  plain-English class to resolve ("wristwatch model"), OR
        class_qid: explicit Wikidata class QID (skips search).
        conditional_property: a PID (e.g. "P176" manufacturer) to group by,
            producing a conditional map keyed by ``parent_column``.
        parent_column: schema column the conditional parent feeds ("brand").
        limit: max entities to fetch.

    Raises ValueError when the topic cannot be resolved or the fetched
    vocabulary fails validation (fewer than 2 usable values).
    """
    resolved_label = topic or class_qid or ""
    if class_qid is None:
        if not topic:
            raise ValueError("Provide either topic or class_qid")
        hit = search_class(topic)
        if hit is None:
            raise ValueError(f"Wikidata search found nothing for topic {topic!r}")
        class_qid, resolved_label = hit

    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    provenance = AssetProvenance(
        source_type="wikidata",
        source_name=f"wikidata:{class_qid}",
        license_name="CC0-1.0",
        attribution=f"Wikidata class {class_qid} ({resolved_label})",
        collected_at=fetched_at,
        metadata={"endpoint": SPARQL_ENDPOINT, "limit": limit},
    )
    capsule = DomainCapsule(domain=domain)

    if conditional_property:
        grouped = fetch_conditional_members(class_qid, conditional_property, limit=limit)
        clean_map: Dict[str, List[str]] = {}
        for parent, members in grouped.items():
            parent_ok = validate_vocabulary([parent])
            members_ok = validate_vocabulary(members)
            if parent_ok.accepted and members_ok.ok:
                clean_map[parent_ok.accepted[0]] = members_ok.accepted
        if len(clean_map) < 2:
            raise ValueError(
                f"Conditional fetch for {class_qid} via {conditional_property} "
                f"produced too few usable groups ({len(clean_map)})"
            )
        capsule.conditional_vocabularies[column.lower()] = {
            "parent": (parent_column or "parent").lower(),
            "map": clean_map,
        }
        # Flat views ride along so single-column sampling works too.
        capsule.record_asset(VocabularyAsset(
            name=(parent_column or "parent").lower(),
            values=sorted(clean_map.keys()),
            provenance=provenance,
        ))
        capsule.record_asset(VocabularyAsset(
            name=column.lower(),
            values=[m for members in clean_map.values() for m in members],
            provenance=provenance,
        ))
        return capsule

    labels = fetch_class_members(class_qid, limit=limit)
    result = validate_vocabulary(labels)
    if not result.ok:
        raise ValueError(
            f"Wikidata class {class_qid} produced too few usable labels "
            f"({result.summary()})"
        )
    capsule.record_asset(VocabularyAsset(
        name=column.lower(),
        values=result.accepted,
        provenance=provenance,
    ))
    return capsule
