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

# name -> {file, keywords, description}. Keyword matching is word-boundary
# based: a single-word keyword must equal a corpus token ("tea" never matches
# "team"); a multi-word keyword matches as a phrase in the normalized corpus.
REGISTRY_INDEX: Dict[str, dict] = {
    "vintage-watches": {
        "file": "vintage-watches.capsule.json",
        "keywords": ("watch", "watches", "wristwatch", "wristwatches", "horology", "timepiece", "timepieces"),
        "description": "Watch brands and model lines (Wikidata Q178794 + curated), brand→model conditional map.",
    },
    "falconry": {
        "file": "falconry.capsule.json",
        "keywords": ("falcon", "falcons", "falconry", "raptor", "raptors", "hawk", "hawks", "birds of prey"),
        "description": "Birds of prey species, training techniques, and falconry equipment.",
    },
    "coral-reef": {
        "file": "coral-reef.capsule.json",
        "keywords": ("coral", "corals", "reef", "reefs"),
        "description": "Coral species, reef survey sites/zones, and survey methods.",
    },
    "aircraft": {
        "file": "aircraft.capsule.json",
        "keywords": ("aircraft", "airplane", "airplanes", "aviation", "airline", "airlines", "airfleet"),
        "description": "Aircraft manufacturers and models (manufacturer→model conditional), aircraft types.",
    },
    "classic-cars": {
        "file": "classic-cars.capsule.json",
        "keywords": ("classic car", "classic cars", "vintage car", "vintage cars", "car auction", "muscle car", "oldtimer", "oldtimers"),
        "description": "Classic car makes and models (make→model conditional), body styles.",
    },
    "bicycles": {
        "file": "bicycles.capsule.json",
        "keywords": ("bicycle", "bicycles", "cycling", "bike", "bikes", "velodrome"),
        "description": "Bicycle types and component groupsets.",
    },
    "sailing": {
        "file": "sailing.capsule.json",
        "keywords": ("sailing", "sailboat", "sailboats", "yacht", "yachts", "marina", "regatta", "boats", "boat"),
        "description": "Boat and rig types for sailing/marina datasets.",
    },
    "sneakers": {
        "file": "sneakers.capsule.json",
        "keywords": ("sneaker", "sneakers", "footwear", "streetwear", "kicks", "shoes", "shoe"),
        "description": "Sneaker brands and models (brand→model conditional), condition grades.",
    },
    "fountain-pens": {
        "file": "fountain-pens.capsule.json",
        "keywords": ("fountain pen", "fountain pens", "pens", "stationery"),
        "description": "Fountain pen brands and models (brand→model conditional), nib sizes, filling systems.",
    },
    "cameras": {
        "file": "cameras.capsule.json",
        "keywords": ("camera", "cameras", "photography", "photographer", "photographers"),
        "description": "Camera brands and models (brand→model conditional), lens mounts, camera types.",
    },
    "guitars": {
        "file": "guitars.capsule.json",
        "keywords": ("guitar", "guitars", "luthier", "luthiers"),
        "description": "Guitar brands and models (brand→model conditional), pickups, instrument types.",
    },
    "whiskey": {
        "file": "whiskey.capsule.json",
        "keywords": ("whiskey", "whisky", "whiskeys", "whiskies", "bourbon", "distillery", "distilleries", "scotch"),
        "description": "Distilleries and expressions (distillery→expression conditional), styles, cask types.",
    },
    "wine": {
        "file": "wine.capsule.json",
        "keywords": ("wine", "wines", "winery", "wineries", "vineyard", "vineyards", "sommelier", "cellar"),
        "description": "Grape varieties, wine regions, and styles.",
    },
    "coffee": {
        "file": "coffee.capsule.json",
        "keywords": ("coffee", "cafe", "cafes", "espresso", "roastery", "roasteries", "barista"),
        "description": "Coffee varieties, origins, roast levels, processes, brew methods.",
    },
    "cheese": {
        "file": "cheese.capsule.json",
        "keywords": ("cheese", "cheeses", "fromagerie", "creamery", "dairy"),
        "description": "Cheese varieties, milk types, and styles.",
    },
    "tea": {
        "file": "tea.capsule.json",
        "keywords": ("tea", "teas", "teahouse", "teahouses"),
        "description": "Tea varieties and types.",
    },
    "dinosaurs": {
        "file": "dinosaurs.capsule.json",
        "keywords": ("dinosaur", "dinosaurs", "paleontology", "fossil", "fossils", "jurassic", "cretaceous"),
        "description": "Dinosaur genera, geological periods, diets.",
    },
    "meteorites": {
        "file": "meteorites.capsule.json",
        "keywords": ("meteorite", "meteorites", "meteor", "meteors", "bolide"),
        "description": "Meteorite classifications and find types.",
    },
    "minerals": {
        "file": "minerals.capsule.json",
        "keywords": ("mineral", "minerals", "gem", "gems", "gemstone", "gemstones", "lapidary", "crystals"),
        "description": "Mineral species, crystal systems, gem cuts.",
    },
    "dog-breeds": {
        "file": "dog-breeds.capsule.json",
        "keywords": ("dog", "dogs", "canine", "canines", "kennel", "kennels", "puppy", "puppies"),
        "description": "Dog breeds and breed groups.",
    },
    "cat-breeds": {
        "file": "cat-breeds.capsule.json",
        "keywords": ("cat", "cats", "feline", "felines", "cattery", "kitten", "kittens"),
        "description": "Cat breeds and coat patterns.",
    },
    "houseplants": {
        "file": "houseplants.capsule.json",
        "keywords": ("houseplant", "houseplants", "plants", "botanical", "greenhouse", "nursery"),
        "description": "Houseplant species and light requirements.",
    },
    "mushrooms": {
        "file": "mushrooms.capsule.json",
        "keywords": ("mushroom", "mushrooms", "fungi", "fungus", "mycology", "foraging"),
        "description": "Mushroom species and habitats.",
    },
    "orchids": {
        "file": "orchids.capsule.json",
        "keywords": ("orchid", "orchids"),
        "description": "Orchid species and growth habits.",
    },
    "classical-music": {
        "file": "classical-music.capsule.json",
        "keywords": ("symphony", "orchestra", "orchestras", "classical", "concerto", "philharmonic", "opera", "conservatory"),
        "description": "Composers, musical forms, and periods.",
    },
    "board-games": {
        "file": "board-games.capsule.json",
        "keywords": ("board game", "board games", "boardgame", "boardgames", "tabletop"),
        "description": "Board game titles and mechanisms.",
    },
    "astronomy": {
        "file": "astronomy.capsule.json",
        "keywords": ("astronomy", "telescope", "telescopes", "observatory", "observatories", "stargazing", "astrophotography"),
        "description": "Deep-sky objects and telescope types.",
    },
    "climbing": {
        "file": "climbing.capsule.json",
        "keywords": ("climbing", "climbers", "bouldering", "crag", "crags", "mountaineering", "belay"),
        "description": "Climbing disciplines, equipment, grades.",
    },
    "scuba-diving": {
        "file": "scuba-diving.capsule.json",
        "keywords": ("scuba", "diving", "divers", "dive", "dives", "snorkeling", "freediving"),
        "description": "Dive types, certification levels, equipment.",
    },
    "beekeeping": {
        "file": "beekeeping.capsule.json",
        "keywords": ("beekeeping", "beekeeper", "beekeepers", "apiary", "apiaries", "hive", "hives", "bees", "honey"),
        "description": "Bee species, hive types, beekeeping equipment.",
    },
    "game-consoles": {
        "file": "game-consoles.capsule.json",
        "keywords": ("console", "consoles", "video game", "video games", "videogame", "videogames", "gaming"),
        "description": "Console manufacturers and models (manufacturer→console conditional), generations.",
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
    """Lowercased, space-normalized text the keyword gate scans."""
    parts = [getattr(config, "name", "") or "", getattr(config, "domain", "") or ""]
    for table in getattr(config, "tables", []) or []:
        parts.append(getattr(table, "name", "") or "")
    return " ".join(parts).lower().replace("_", " ").replace("-", " ")


def _keyword_hits(keywords, corpus: str) -> bool:
    """Word-boundary keyword match: single-word keywords must equal a corpus
    token ("tea" never matches "team"); multi-word keywords match as phrases."""
    import re as _re
    tokens = set(_re.findall(r"[a-z]+", corpus))
    for kw in keywords:
        if " " in kw:
            if kw in corpus:
                return True
        elif kw in tokens:
            return True
    return False


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
        if not _keyword_hits(entry["keywords"], corpus):
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
