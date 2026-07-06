"""Design-time vocabulary auto-discovery: unknown column → Wikidata → verified capsule.

This is the "intelligent" layer of the vocabulary architecture, and it is
deliberately NOT wired into generation. Discovery runs at schema-design time
(a CLI action, a studio button, an explicit ``enrich_schema_vocabulary``
call), spends the network once, caches what it finds, and attaches the result
to the schema with visible provenance so a human can veto a bad match.

The verification loop is what makes it trustworthy rather than confident and
wrong:

  1. Candidate search terms come from the column and its table
     ("meteorites" table, "classification" column → "meteorite
     classification", "meteorite").
  2. ``wbsearchentities`` proposes entity candidates; candidates whose
     description marks them as the WRONG kind of thing (family names, films,
     albums, places) are rejected before any fetch.
  3. Each surviving candidate class is verified by actually sampling its
     instances; the vocabulary validator filters the labels, and a candidate
     only wins with enough usable values.
  4. The winner attaches with its QID recorded, so "vocabulary fetched from
     wikidata:QXXX (label)" is auditable and reversible.

Results are cached in ``~/.misata/wikidata_discovery.json`` so repeated
designs of the same column cost zero network.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from misata.vocab_validator import validate_vocabulary

_CACHE_PATH = Path.home() / ".misata" / "wikidata_discovery.json"
_MIN_USABLE_VALUES = 8
_MAX_CANDIDATES_PER_TERM = 4

# Candidate descriptions that mark an entity as the wrong KIND of thing for a
# vocabulary class ("Falcon" the family name, "Watch" the 1978 album).
_DESCRIPTION_DENYLIST = (
    "family name", "given name", "surname", "male given name",
    "female given name", "album", "film", "song", "single by",
    "episode", "band", "state of", "municipality", "commune",
    "village", "city in", "town in", "wikimedia disambiguation",
    "scientific article", "human settlement", "surname",
)

# Column names the engine already handles with dedicated realism paths;
# discovery must not fight them.
_HANDLED_COLUMNS = {
    "id", "name", "first_name", "last_name", "full_name", "email", "phone",
    "address", "city", "country", "state", "region", "zip", "postal_code",
    "url", "website", "username", "password", "description", "notes",
    "created_at", "updated_at", "status", "date", "company", "title",
}

# Entity-like column names that are worth a discovery attempt when the
# domain is unknown. Suffix or exact match.
_ENTITY_COLUMN_HINTS = (
    "species", "breed", "genus", "variety", "varietal", "classification",
    "model", "make", "brand", "cultivar", "instrument", "mineral",
    "compound", "material", "style", "discipline", "technique", "genre",
)


@dataclass
class Discovery:
    """One column's discovery outcome."""

    table: str
    column: str
    term: str = ""
    qid: str = ""
    label: str = ""
    values: List[str] = field(default_factory=list)
    attached: bool = False
    reason: str = ""

    def note(self) -> str:
        if self.attached:
            return (f"{self.table}.{self.column}: {len(self.values)} values "
                    f"from wikidata:{self.qid} ({self.label})")
        return f"{self.table}.{self.column}: not attached ({self.reason})"


def _load_cache() -> Dict[str, dict]:
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(cache: Dict[str, dict]) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, indent=1, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass  # cache is an optimization, never a failure


def _singular(word: str) -> str:
    w = word.strip().lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("es") and len(w) > 4 and w[-3] in "sxzh":
        return w[:-2]
    if w.endswith("s") and len(w) > 3:
        return w[:-1]
    return w


def _search_terms(table: str, column: str, domain_hint: str = "") -> List[str]:
    """Ordered candidate search phrases, most specific first."""
    t = _singular(table.replace("_", " "))
    c = column.replace("_", " ").strip().lower()
    terms = []
    if domain_hint:
        terms.append(f"{_singular(domain_hint)} {c}")
    terms.append(f"{t} {c}")
    terms.append(t)
    if c not in ("name", "label", "type"):
        terms.append(c)
    # dedupe, preserve order
    seen, out = set(), []
    for term in terms:
        term = term.strip()
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def _search_candidates(term: str) -> List[dict]:
    """wbsearchentities hits with wrong-kind descriptions filtered out."""
    import urllib.parse
    import urllib.request
    from misata.wikidata import SEARCH_ENDPOINT, USER_AGENT
    url = SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({
        "action": "wbsearchentities", "search": term, "language": "en",
        "type": "item", "format": "json", "limit": _MAX_CANDIDATES_PER_TERM + 3,
    })
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    out = []
    for hit in raw.get("search", []):
        desc = (hit.get("description") or "").lower()
        if any(bad in desc for bad in _DESCRIPTION_DENYLIST):
            continue
        out.append({"qid": hit["id"], "label": hit.get("label", term), "description": desc})
        if len(out) >= _MAX_CANDIDATES_PER_TERM:
            break
    return out


def discover_column(
    table: str,
    column: str,
    domain_hint: str = "",
    sparql_pause: float = 1.0,
    use_cache: bool = True,
) -> Discovery:
    """Resolve one column to a verified Wikidata vocabulary, or explain why not."""
    from misata.wikidata import fetch_class_members

    d = Discovery(table=table, column=column)
    cache = _load_cache() if use_cache else {}

    for term in _search_terms(table, column, domain_hint):
        cache_key = term.lower()
        if cache_key in cache:
            hit = cache[cache_key]
            if hit.get("values"):
                d.term, d.qid, d.label = term, hit["qid"], hit["label"]
                d.values = hit["values"]
                d.attached = True
                return d
            continue  # negative-cached term

        try:
            candidates = _search_candidates(term)
        except Exception as exc:
            d.reason = f"search failed: {exc}"
            return d

        for cand in candidates:
            try:
                labels = fetch_class_members(cand["qid"], limit=120)
            except Exception as exc:
                # SPARQL throttling (outage windows rate-limit hard) — stop
                # discovery gracefully rather than hammering the endpoint.
                d.reason = f"sparql unavailable: {str(exc)[:80]}"
                return d
            time.sleep(max(0.0, sparql_pause))
            result = validate_vocabulary(labels)
            if len(result.accepted) >= _MIN_USABLE_VALUES:
                d.term, d.qid, d.label = term, cand["qid"], cand["label"]
                d.values = result.accepted
                d.attached = True
                cache[cache_key] = {"qid": d.qid, "label": d.label, "values": d.values}
                _save_cache(cache)
                return d

        cache[cache_key] = {"qid": "", "label": "", "values": []}
        _save_cache(cache)

    d.reason = "no candidate class produced enough verified values"
    return d


def _is_discovery_candidate(col, covered: set) -> bool:
    if getattr(col, "type", "") != "text":
        return False
    name = getattr(col, "name", "").lower()
    if name in _HANDLED_COLUMNS or name.endswith("_id"):
        return False
    if name in covered:
        return False
    params = getattr(col, "distribution_params", {}) or {}
    if params.get("choices") or params.get("pattern") or params.get("formula") \
            or params.get("text_type"):
        return False
    return name in _ENTITY_COLUMN_HINTS or name.endswith(tuple("_" + h for h in _ENTITY_COLUMN_HINTS))


def enrich_schema_vocabulary(
    config,
    sparql_pause: float = 1.0,
    max_columns: int = 5,
    use_cache: bool = True,
) -> List[Discovery]:
    """Discover and attach vocabulary for a schema's open entity columns.

    Mutates ``config.vocabularies`` for every successful discovery and
    returns the full report (attached or not, with reasons) so callers can
    show the human what was fetched and from where. Columns already covered
    by the schema's vocabulary block or a registry capsule are skipped.
    """
    from misata.capsule_registry import load_registry_capsule, match_registry_capsules

    covered = {k.lower() for k in (getattr(config, "vocabularies", None) or {})}
    for reg_name in match_registry_capsules(config):
        cap = load_registry_capsule(reg_name)
        covered |= set(cap.vocabularies) | set(cap.conditional_vocabularies)

    report: List[Discovery] = []
    domain_hint = getattr(config, "domain", "") or getattr(config, "name", "") or ""
    for table in getattr(config, "tables", []) or []:
        for col in (getattr(config, "columns", {}) or {}).get(table.name, []):
            if len(report) >= max_columns:
                return report
            if not _is_discovery_candidate(col, covered):
                continue
            d = discover_column(table.name, col.name, domain_hint=domain_hint,
                                sparql_pause=sparql_pause, use_cache=use_cache)
            report.append(d)
            if d.attached:
                if getattr(config, "vocabularies", None) is None:
                    config.vocabularies = {}
                config.vocabularies[col.name.lower()] = d.values
                covered.add(col.name.lower())
    return report
