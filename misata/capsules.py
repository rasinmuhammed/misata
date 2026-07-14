"""
Capsule registry: shareable, reviewable domain vocabulary packs.

A capsule is one JSON file holding everything Misata needs to speak a
domain's language: named vocabularies (species, treatments, drone models —
whatever the domain calls things) with provenance for every list. The
engine stays deterministic and LLM-free at generation time; intelligence
is spent ONCE, at capsule creation, by whoever (or whatever) has it:

  - ``capsule_from_dataframes``: mine vocabularies from example data the
    user already has (a CSV export, a sample dump). Zero LLM, zero cost.
  - ``capsule_from_llm``: have an LLM (BYO key, e.g. Groq's free tier)
    write the vocabulary pools once; the file is cached, reviewable, and
    versionable. Falls back to curated pools without a key.
  - hand-written: it's JSON — edit it, commit it, share it.

Because a capsule is a file, it is also a community artifact: a
``veterinary.capsule.json`` made by one user works for everyone, which is
the distribution model (git, gists, HF datasets) without a server.

Generation hookup: ``misata.generate(story, capsule="vet.capsule.json")``
or ``realism: {capsule_file: ...}`` in YAML. Capsule vocabularies take
priority over built-in pools for matching semantic types.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from misata.domain_capsule import AssetProvenance, DomainCapsule, VocabularyAsset

CAPSULE_FORMAT_VERSION = 1

# Column-name fragments that mark values as identity-like or free-text —
# never worth mining into a vocabulary.
_SKIP_COLUMN_HINTS = (
    "id", "uuid", "email", "phone", "password", "token", "hash", "url",
    "address", "ip", "ssn", "iban", "date", "time", "_at",
)


def save_capsule(capsule: DomainCapsule, path: Union[str, Path]) -> Path:
    """Write a capsule to a single shareable JSON file."""
    out = Path(path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {
        "misata_capsule": CAPSULE_FORMAT_VERSION,
        "domain": capsule.domain,
        "locale": capsule.locale,
        "era": capsule.era,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "metadata": capsule.metadata,
        "vocabularies": capsule.vocabularies,
        "conditional_vocabularies": capsule.conditional_vocabularies,
        "price_bands": capsule.price_bands,
        "provenance": {
            name: [
                {
                    "source_type": p.source_type,
                    "source_name": p.source_name,
                    "license_name": p.license_name,
                    "attribution": p.attribution,
                    "collected_at": p.collected_at,
                    "metadata": p.metadata,
                }
                for p in provs
            ]
            for name, provs in capsule.provenance.items()
        },
    }
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def load_capsule(path: Union[str, Path]) -> DomainCapsule:
    """Load a capsule file saved by :func:`save_capsule` (or hand-written)."""
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    version = raw.get("misata_capsule")
    if version != CAPSULE_FORMAT_VERSION:
        raise ValueError(
            f"'{path}' is not a Misata capsule (or unsupported version {version!r}); "
            f"expected top-level \"misata_capsule\": {CAPSULE_FORMAT_VERSION}."
        )
    capsule = DomainCapsule(
        domain=raw.get("domain", "generic"),
        locale=raw.get("locale", "global"),
        era=raw.get("era"),
        metadata=dict(raw.get("metadata", {})),
    )
    provenance_raw = raw.get("provenance", {})
    for name, values in raw.get("vocabularies", {}).items():
        values = [str(v) for v in values if str(v).strip()]
        if not values:
            continue
        prov_entries = provenance_raw.get(name) or [{
            "source_type": "capsule_file",
            "source_name": str(path),
            "license_name": "unspecified",
        }]
        capsule.record_asset(
            VocabularyAsset(
                name=name,
                values=values,
                provenance=AssetProvenance(
                    source_type=prov_entries[0].get("source_type", "capsule_file"),
                    source_name=prov_entries[0].get("source_name", str(path)),
                    license_name=prov_entries[0].get("license_name", "unspecified"),
                    attribution=prov_entries[0].get("attribution"),
                    collected_at=prov_entries[0].get("collected_at"),
                    metadata=dict(prov_entries[0].get("metadata", {})),
                ),
                domain=capsule.domain,
                locale=capsule.locale,
            )
        )
    # Conditional maps (brand→model): keys normalized to lowercase column names.
    for child, spec in (raw.get("conditional_vocabularies") or {}).items():
        if isinstance(spec, dict) and isinstance(spec.get("map"), dict) and spec.get("parent"):
            capsule.conditional_vocabularies[str(child).lower()] = {
                "parent": str(spec["parent"]).lower(),
                "map": {
                    str(k): [str(v) for v in vals]
                    for k, vals in spec["map"].items()
                    if isinstance(vals, (list, tuple)) and vals
                },
            }
    # Price bands (category→[min,max]): a row's price stays inside the band
    # of its category value.
    for child, spec in (raw.get("price_bands") or {}).items():
        if isinstance(spec, dict) and isinstance(spec.get("bands"), dict) and spec.get("parent"):
            bands = {}
            for k, band in spec["bands"].items():
                if (isinstance(band, (list, tuple)) and len(band) == 2
                        and all(isinstance(x, (int, float)) for x in band)
                        and float(band[0]) <= float(band[1])):
                    bands[str(k)] = [float(band[0]), float(band[1])]
            if bands:
                capsule.price_bands[str(child).lower()] = {
                    "parent": str(spec["parent"]).lower(),
                    "bands": bands,
                }
    return capsule


def merge_into(base: DomainCapsule, overlay: DomainCapsule) -> DomainCapsule:
    """Overlay capsule vocabularies onto a base capsule (overlay wins).

    Used at generation time so a user capsule beats built-in fallbacks for
    the same semantic name while leaving everything else intact.
    """
    for name, values in overlay.vocabularies.items():
        base.vocabularies[name] = list(values)
        base.provenance[name] = list(overlay.provenance.get(name, []))
    for child, spec in overlay.conditional_vocabularies.items():
        base.conditional_vocabularies[child] = spec
    for child, spec in overlay.price_bands.items():
        base.price_bands[child] = spec
    base.metadata.setdefault("capsule_overlays", []).append(overlay.domain)
    return base


def capsule_from_dataframes(
    domain: str,
    tables: Dict[str, Any],
    *,
    max_values: int = 200,
    min_distinct: int = 2,
    columns: Optional[List[str]] = None,
) -> DomainCapsule:
    """Mine a capsule from example data — no LLM, no network, no cost.

    String/categorical columns with reasonable cardinality become
    vocabularies, keyed by the inferred semantic name when one exists
    (so ``product`` columns feed Misata's product generation) and by the
    raw column name otherwise. Identity-like columns (ids, emails,
    timestamps) are skipped.
    """
    from misata.vocabulary import SemanticVocabularyGenerator

    inferrer = SemanticVocabularyGenerator()
    capsule = DomainCapsule(domain=domain, metadata={"mined_from": list(tables.keys())})

    for table_name, df in tables.items():
        for col in df.columns:
            col_lower = str(col).lower()
            if columns is not None and col not in columns:
                continue
            if columns is None and any(h in col_lower for h in _SKIP_COLUMN_HINTS):
                continue
            series = df[col]
            if series.dtype.kind not in ("O", "U", "S"):  # strings only
                continue
            distinct = (
                series.dropna().astype(str).str.strip().replace("", None).dropna().unique()
            )
            if not (min_distinct <= len(distinct) <= max_values):
                continue
            semantic = inferrer._infer_semantic(col_lower, table_name)
            if not semantic or semantic == "generic":
                # No real semantic match — key by column name so any column
                # with the same name picks the vocabulary up directly.
                semantic = col_lower
            capsule.record_asset(
                VocabularyAsset(
                    name=semantic,
                    values=sorted(distinct.tolist()),
                    provenance=AssetProvenance(
                        source_type="mined_dataframe",
                        source_name=f"{table_name}.{col}",
                        license_name="user-data",
                        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    ),
                    domain=domain,
                )
            )
    return capsule


def capsule_from_llm(
    domain: str,
    vocab_names: List[str],
    *,
    context: str = "",
    size: int = 80,
    use_llm: bool = True,
) -> DomainCapsule:
    """Create a capsule by spending intelligence once.

    Each requested vocabulary is generated by the configured LLM provider
    (see :mod:`misata.smart_values`; BYO key) and falls back to curated
    pools when no key is available — the call never fails for lack of one.
    The result is meant to be SAVED and reviewed: generation afterwards is
    deterministic and offline.
    """
    from misata.smart_values import SmartValueGenerator

    generator = SmartValueGenerator()
    capsule = DomainCapsule(domain=domain, metadata={"requested": vocab_names})
    for name in vocab_names:
        values = generator.get_pool(
            column_name=name,
            table_name=domain,
            domain_hint=domain,
            context=context or f"{domain} domain",
            size=size,
            use_llm=use_llm,
        ) or []
        if not values:
            continue
        capsule.record_asset(
            VocabularyAsset(
                name=name,
                values=[str(v) for v in values],
                provenance=AssetProvenance(
                    source_type="llm" if use_llm else "curated_pool",
                    source_name=f"smart_values:{domain}/{name}",
                    license_name="generated",
                    collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                ),
                domain=domain,
            )
        )
    return capsule
