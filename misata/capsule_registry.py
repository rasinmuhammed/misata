"""Bundled capsule registry: curated vocabulary packs that ship with Misata.

Phase 3 of the vocabulary architecture. Each registry capsule is a normal
capsule JSON (provenance included) packaged inside the wheel, so niche
domains get real vocabulary offline, deterministically, with no LLM and no
network. `misata capsule registry` lists them; `misata capsule install NAME`
copies one to ~/.misata/capsules for editing; and ``auto_attach_capsules``
lets the simulator adopt a matching capsule automatically.

Auto-attach is deliberately conservative — it requires BOTH signals:
  1. a domain keyword match in the schema's table names / schema name /
     declared domain ("watches" table → the vintage-watches capsule), AND
  2. at least one schema column whose name the capsule actually covers.
A "products" table with brand+model columns must NOT get watch models; the
keyword gate is what prevents that.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Dict, List, Optional

from misata.domain_capsule import DomainCapsule

_REGISTRY_DIR = Path(__file__).parent / "capsules_registry"
_USER_CAPSULE_DIR = Path.home() / ".misata" / "capsules"

# name -> (filename, domain keywords that gate auto-attach)
REGISTRY_INDEX: Dict[str, dict] = {
    "vintage-watches": {
        "file": "vintage-watches.capsule.json",
        "keywords": ("watch", "horolog", "timepiece", "wristwatch"),
        "description": "Watch brands and model lines (Wikidata Q178794 + curated), brand→model conditional map.",
    },
    "falconry": {
        "file": "falconry.capsule.json",
        "keywords": ("falcon", "raptor", "hawk", "falconry", "bird_of_prey", "birds_of_prey"),
        "description": "Birds of prey species, training techniques, and falconry equipment.",
    },
    "coral-reef": {
        "file": "coral-reef.capsule.json",
        "keywords": ("coral", "reef"),
        "description": "Coral species, reef survey sites/zones, and survey methods.",
    },
}


def registry_names() -> List[str]:
    return sorted(REGISTRY_INDEX)


def registry_path(name: str) -> Path:
    entry = REGISTRY_INDEX.get(name)
    if entry is None:
        raise KeyError(f"No registry capsule named {name!r}. Available: {registry_names()}")
    return _REGISTRY_DIR / entry["file"]


def load_registry_capsule(name: str) -> DomainCapsule:
    from misata.capsules import load_capsule
    return load_capsule(registry_path(name))


def install_capsule(name: str, dest_dir: Optional[Path] = None) -> Path:
    """Copy a registry capsule into the user's capsule directory for editing."""
    src = registry_path(name)
    dest_dir = Path(dest_dir) if dest_dir else _USER_CAPSULE_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / src.name
    shutil.copyfile(src, dest)
    return dest


def _schema_corpus(config) -> str:
    """Lowercased text the keyword gate scans: table names, schema name, domain."""
    parts = [getattr(config, "name", "") or "", getattr(config, "domain", "") or ""]
    for table in getattr(config, "tables", []) or []:
        parts.append(getattr(table, "name", "") or "")
    return " ".join(parts).lower()


def _schema_columns(config) -> set:
    cols = set()
    for col_list in (getattr(config, "columns", {}) or {}).values():
        for col in col_list:
            cols.add(getattr(col, "name", "").lower())
    return cols


def match_registry_capsules(config) -> List[str]:
    """Registry capsule names whose keyword gate AND column coverage both hit."""
    corpus = _schema_corpus(config)
    columns = _schema_columns(config)
    matches: List[str] = []
    for name, entry in REGISTRY_INDEX.items():
        if not any(kw in corpus for kw in entry["keywords"]):
            continue
        try:
            capsule = load_registry_capsule(name)
        except Exception:
            continue
        covered = set(capsule.vocabularies) | set(capsule.conditional_vocabularies)
        for cond in capsule.conditional_vocabularies.values():
            covered.add(str(cond.get("parent", "")).lower())
        if columns & covered:
            matches.append(name)
    return matches


def auto_attach_capsules(config, base_capsule: DomainCapsule) -> List[str]:
    """Merge matching registry capsules into the generation capsule.

    Returns the names attached. User-supplied capsules are merged AFTER this
    in the simulator, so an explicit capsule always beats the registry.
    """
    from misata.capsules import merge_into
    attached = []
    for name in match_registry_capsules(config):
        merge_into(base_capsule, load_registry_capsule(name))
        attached.append(name)
    return attached
