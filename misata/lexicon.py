"""Generative lexicons: unbounded, believable values from a small readable spec.

A pool of values cannot be realistic, and not because it is too small. What
makes a vocabulary believable is its TAIL, and the tail is unbounded by
definition. That is Heaps' law, and a finite pool of any size has a Heaps
exponent of zero asymptotically, so ten million listed values fail exactly as
two hundred and eighty five do, only later. Measured on this engine before
this module existed: 285 distinct words across 372,622 tokens of review text,
Heaps exponent 0.000, 49.9% of reviews byte-identical to another one.

Generative Lexicon theory has the answer, and it is how human language itself
gets unbounded vocabulary out of finite memory:

    list the frequent and idiosyncratic forms,
    compose the forms which are not listed.

Nobody memorised "MV Meridian Voyager". It was composed, and it reads as a
ship because it obeys the morphology of ship names. So a spec carries a small
HEAD of real, irregular, memorable values plus the productive machinery for
everything else. The head is drawn often and each composed value rarely, which
is not an approximation of Zipf's law but the mechanism that produces it.

Two properties follow that the previous approach could not have:

* **Vocabulary keeps growing.** The composed tail mints new types as the table
  grows, so the Heaps exponent is positive by construction.
* **Cross-type collision becomes impossible.** One spec per semantic type means
  a plan tier has no path into a person-name column. Before this, thirteen
  distinct column names (``full_name``, ``ceo_name``, ``vessel_name``,
  ``chemical_name`` among them) all resolved to the same three-word pool.

The honest limit, learned by building it: statistics are necessary and never
sufficient. Expanding morphemes mechanically hits every target (Heaps 0.988,
9.2% duplicates) and emits "Michaelyn McHughes". Morphemes must be real
morphemes. Where scale is needed, the pools come from real sources.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
from pydantic import BaseModel, Field, field_validator

_SLOT = re.compile(r"\{(\w+)\}")
_WS = re.compile(r"\s+")

Pool = Union[List[str], Dict[str, float]]



_GEMINABLE = set("bcdfgklmnprstvwz")


def _degeminate_join(left: str, right: str) -> str:
    """Concatenate two morphemes the way English orthography does.

    Hart + ton is written Harton and Ell + ley is written Elley, so a composer
    that concatenates blindly produces spellings no surname has. Only the two
    characters that meet are considered: run this over a whole string instead
    and "Bell" comes out "Bel", which is the same class of error pointing the
    other way.
    """
    if not left or not right:
        return left + right
    a, b = left[-1], right[0]
    if a.lower() == b.lower() and a.lower() in _GEMINABLE:
        return left + right[1:]
    return left + right


class LexiconSpec(BaseModel):
    """How a kind of value is formed. Small enough for a human to audit.

    A 900-line spec can be read in five minutes and corrected by someone who
    knows the domain ("tankers take MT, not MV"). Neither a seven-million-value
    pool nor a model's weights can be reviewed by anyone, and this spec ships
    with the data, so a reader can see exactly how a value was made.

    Attributes:
        name: The semantic type this answers for. One spec per type is what
            makes a cross-type collision impossible rather than unlikely.
        head: Real, high-frequency, often irregular values, most frequent
            first. Drawn with Zipfian weight over rank, because a uniform head
            would itself be a tell.
        head_share: Probability a draw comes from the head at all. Sets how
            much the column repeats. Clinical coding concentrates heavily on
            common procedures; customer surnames do not.
        slots: Morpheme pools. A list is uniform, a dict carries weights.
        patterns: Composition templates over slots, with weights.
        distinct_slots: Slot groups that must not take the same value inside
            one composition, so "Ocean Ocean" cannot be emitted.
        blocklist: Exact strings composition must never produce.
        rows_per_distinct: How many rows a real column of this type carries per
            distinct value. Repetition is not a defect, it is a property of the
            type: clinical coding concentrates on a handful of procedures, so
            30,000 rows over a few thousand distinct is what real data looks
            like, while 30,000 customers sharing 2,000 names is not. Feasibility
            refuses only a column MORE degenerate than its type naturally is.
        elide_boundary_doubles: Collapse a consonant repeated across a morpheme
            join, the way English orthography does. Without it "Hart" + "ton"
            emits "Hartton" and "Ell" + "ley" emits "Ellley" — a defect that
            only shows up when every pairing is enumerated, because it hides in
            twelve of two hundred and sixty and sampling never lands on it.
    """

    name: str
    head: List[str] = Field(default_factory=list)
    head_share: float = Field(default=0.05, ge=0.0, le=1.0)
    slots: Dict[str, Pool] = Field(default_factory=dict)
    patterns: List[Tuple[str, float]] = Field(default_factory=list)
    distinct_slots: List[List[str]] = Field(default_factory=list)
    blocklist: List[str] = Field(default_factory=list)
    rows_per_distinct: float = Field(default=2.0, gt=0.0)
    elide_boundary_doubles: bool = False
    # True when an existing locale-aware provider already answers this type
    # better than composition can. Person names are region-specific and the
    # locale machinery gets them right; a lexicon that overrode it would
    # replace Japanese names with English ones, which is a regression dressed
    # as an improvement.
    locale_sensitive: bool = False
    description: Optional[str] = None

    @field_validator("patterns")
    @classmethod
    def _patterns_have_weight(cls, v):
        for pat, w in v:
            if w <= 0:
                raise ValueError(f"pattern {pat!r} has non-positive weight {w}")
        return v

    # ---- capacity -------------------------------------------------------
    def _pool(self, slot: str) -> Tuple[List[str], Optional[np.ndarray]]:
        raw = self.slots.get(slot)
        if raw is None:
            return [""], None
        if isinstance(raw, dict):
            keys = list(raw)
            w = np.asarray([float(raw[k]) for k in keys], dtype=float)
            return keys, (w / w.sum() if w.sum() else None)
        return list(raw), None

    def raw_capacity(self) -> int:
        """Distinct strings reachable at all. Do not size a table with this."""
        total = len(self.head)
        for pat, _w in self.patterns:
            n = 1
            for slot in _SLOT.findall(pat):
                n *= max(1, len(self._pool(slot)[0]))
            total += n
        return total

    def effective_capacity(self) -> int:
        """Rows this spec can serve before the busiest pattern starts repeating.

        Raw capacity misleads whenever patterns carry different weights. A
        pattern drawn 86% of the time with 36,000 reachable strings saturates
        long before a rare pattern with ten million, and a column duplicates at
        the rate of whichever pattern saturates FIRST. Measured: raw capacity
        for a person-name spec read 13,863,212 while the honest figure was
        46,860, a 300-fold overstatement that would have told a user their
        100,000-row column was fine before shipping it 52% duplicated.
        """
        if not self.patterns:
            return len(self.head)
        wsum = sum(w for _p, w in self.patterns) or 1.0
        worst: Optional[float] = None
        for pat, w in self.patterns:
            n = 1
            for slot in _SLOT.findall(pat):
                n *= max(1, len(self._pool(slot)[0]))
            share = w / wsum
            if share <= 0:
                continue
            eff = n / share
            worst = eff if worst is None else min(worst, eff)
        return int(worst or 0)


class Lexicon:
    """Deterministic expansion of a :class:`LexiconSpec`."""

    def __init__(self, spec: LexiconSpec, rng: Optional[np.random.Generator] = None):
        self.spec = spec
        self.rng = rng or np.random.default_rng(0)
        n = len(spec.head)
        if n:
            w = 1.0 / np.arange(1, n + 1)
            self._head_w = w / w.sum()
        else:
            self._head_w = np.array([])
        pw = np.asarray([w for _p, w in spec.patterns], dtype=float) if spec.patterns else np.array([])
        self._pat_w = pw / pw.sum() if pw.size else pw
        self._pools = {s: spec._pool(s) for s in spec.slots}
        self._blocked = frozenset(spec.blocklist)
        self._split_cache: Dict[str, List[str]] = {}

    def _join(self, pat: str, chosen: Dict[str, str]) -> str:
        """Fill a pattern, eliding a doubled consonant only where two
        morphemes actually touch.

        The pattern's split is cached: it depends on the pattern alone, and
        recomputing it per value made a regex split the third-hottest call in
        the whole engine.
        """
        if not self.spec.elide_boundary_doubles:
            return _SLOT.sub(lambda m: chosen.get(m.group(1), ""), pat)
        pieces = self._split_cache.get(pat)
        if pieces is None:
            pieces = self._split_cache[pat] = _SLOT.split(pat)
        out = ""
        for piece in pieces:
            out = _degeminate_join(out, chosen.get(piece, piece)
                                   if piece in chosen else piece)
        return out

    def _finish(self, pat: str, chosen: Dict[str, str]) -> str:
        return _WS.sub(" ", self._join(pat, chosen)).strip()

    def _acceptable(self, value: str, chosen: Dict[str, str]) -> bool:
        if not value or value in self._blocked:
            return False
        for grp in self.spec.distinct_slots:
            picked = [chosen[g] for g in grp if g in chosen]
            if len(picked) != len(set(picked)):
                return False
        return True

    def _compose_many(self, n: int) -> List[str]:
        """Compose `n` values with one RNG call per (pattern, slot), not per value.

        The obvious loop draws a pattern and then each slot separately for every
        single value, and a numpy Generator call costs about 14 microseconds
        however small the draw is. That put person_name at 7,400 values a second,
        which is two minutes of wall clock for a million-row column and was 89%
        of total generation time on a 220,000-row schema. Batching pays that cost
        once per group instead of once per value.

        Rejection still works, and still per value: a composition that repeats a
        distinct_slots value or lands on the blocklist is retried in the next
        round, so the guarantee is unchanged and only its cost moved.
        """
        out: List[str] = [""] * n
        pending = np.arange(n)

        for _attempt in range(8):
            if pending.size == 0:
                break
            pat_idx = self.rng.choice(len(self.spec.patterns), size=pending.size,
                                      p=self._pat_w)
            failed: List[int] = []

            for p in np.unique(pat_idx):
                rows = pending[pat_idx == p]
                pat = self.spec.patterns[int(p)][0]
                # A slot repeated in one pattern was already drawn once by the
                # per-value version, because the dict overwrote it. Same here.
                slots = list(dict.fromkeys(_SLOT.findall(pat)))
                drawn: Dict[str, List[str]] = {}
                for slot in slots:
                    keys, w = self._pools.get(slot, ([""], None))
                    # Indices rather than objects: numpy choosing among Python
                    # strings copies them, choosing among ints does not.
                    sel = self.rng.choice(len(keys), size=rows.size, p=w)
                    drawn[slot] = [keys[i] for i in sel]

                for k, row in enumerate(rows):
                    chosen = {slot: drawn[slot][k] for slot in slots}
                    value = self._finish(pat, chosen)
                    if self._acceptable(value, chosen):
                        out[row] = value
                    else:
                        failed.append(int(row))

            pending = np.asarray(failed, dtype=int)

        # Whatever never composed falls back, exactly as before.
        if pending.size:
            fallback = self.spec.head[0] if self.spec.head else ""
            for row in pending:
                out[row] = fallback
        return out

    def _compose_one(self) -> str:
        """One value. Kept for callers that want a single composition."""
        return self._compose_many(1)[0]

    def draw(self, size: int) -> np.ndarray:
        """`size` values. Head draws repeat; composed draws mint new types."""
        spec = self.spec
        out = np.empty(size, dtype=object)
        use_head = (self.rng.random(size) < spec.head_share) if spec.head else np.zeros(size, bool)
        n_head = int(use_head.sum())
        if n_head:
            idx = self.rng.choice(len(spec.head), size=n_head, p=self._head_w)
            out[use_head] = [spec.head[i] for i in idx]
        todo = np.nonzero(~use_head)[0]
        if todo.size:
            out[todo] = self._compose_many(int(todo.size))
        return out


# ---------------------------------------------------------------------------
# Built-in specs
#
# Morphemes come from the largest REAL source available, never from mechanical
# mutation of a smaller one. Expanding 162 first names into 1,200 by appending
# suffixes hits every statistical target and emits "Michaelyn McHughes", which
# is a worse column than the one it replaced. Faker ships 690 given names and
# 1,000 surnames; a capsule or a user list overrides either.
# ---------------------------------------------------------------------------

def _person_pools() -> Tuple[List[str], List[str]]:
    try:
        from faker.providers.person.en_US import Provider as P
        given = sorted({str(x) for x in P.first_names})
        family = sorted({str(x) for x in P.last_names})
        if len(given) > 100 and len(family) > 100:
            return given, family
    except Exception:
        pass
    from misata.vocab_seeds import FIRST_NAMES, LAST_NAMES
    return list(FIRST_NAMES), list(LAST_NAMES)


def _build_builtins() -> Dict[str, LexiconSpec]:
    given, family = _person_pools()

    person = LexiconSpec(
        name="person_name",
        description="Given plus family name, with the very common full names that genuinely recur.",
        head=["James Smith", "Mary Johnson", "John Williams", "Robert Brown",
              "Maria Garcia", "David Miller", "Michael Davis", "Patricia Jones"],
        head_share=0.02,
        slots={"given": given, "family": family,
               "initial": [f"{c}." for c in "ABCDEFGHJKLMNPRSTW"],
               # Surnames also COMPOSE, and the tail of a real surname
               # distribution is where the composed ones live. A provider's
               # thousand-name list puts a hundred people per surname in a
               # hundred-thousand-row table, which is a tell no amount of
               # value-level variety hides. Morphemes stay inside one naming
               # tradition, because crossing traditions is what turns
               # composition into nonsense: an Irish prefix on an English root
               # is not a rare surname, it is not a surname.
               "anglo_stem": ("Ash Brad Whit Hart Nor Sut Wes Ell Har Kirk Mars Nether Pen Rad "
                              "Shel Stan Thorn Wal Wex Bram Cald Dun Farn Gres Hal Old").split(),
               "anglo_suffix": ("ton field wood ford worth bury ley don ridge brook").split(),
               "nordic_stem": ("Erik Ander Lar Nil Sven Karl Bjorn Olaf Peter Johan Henrik "
                               "Gunnar Sigurd Halvor Jen").split(),
               "nordic_suffix": ["sson", "sen", "son"]},
        patterns=[("{given} {family}", 0.80), ("{given} {initial} {family}", 0.11),
                  ("{given} {anglo_stem}{anglo_suffix}", 0.06),
                  ("{given} {nordic_stem}{nordic_suffix}", 0.03)],
        rows_per_distinct=1.6,   # people mostly differ
        elide_boundary_doubles=True,
        locale_sensitive=True,   # the locale pack owns region-correct names
    )

    company = LexiconSpec(
        name="company_name",
        description="Root plus sector plus legal suffix, the ordinary morphology of trading names.",
        head=["Acme Corporation", "Globex", "Initech", "Umbrella Industries"],
        head_share=0.03,
        slots={
            "root": ("Apex Zenith Summit Vertex Northwind Blue Silver Iron Cedar Granite Harbor "
                     "Lumen Pioneer Meridian Atlas Orion Vantage Bright Clarion Quanta Vector "
                     "Nimbus Cobalt Ridge Sterling Pinnacle Anchor Beacon Compass Foundry "
                     "Keystone Lattice Monarch Northgate Oakline Pathway Quarry Redwood Signal "
                     "Trailhead Union Vista Westfield Ironwood Kestrel Lakeshore Marlow Everly").split(),
            "root2": ("Apex Zenith Summit Vertex Northwind Blue Silver Iron Cedar Granite Harbor "
                      "Lumen Pioneer Meridian Atlas Orion Vantage Bright Clarion Quanta Vector "
                      "Nimbus Cobalt Ridge Sterling Pinnacle Anchor Beacon Compass Foundry "
                      "Keystone Lattice Monarch Northgate Oakline Pathway Quarry Redwood Signal "
                      "Trailhead Union Vista Westfield Ironwood Kestrel Lakeshore Marlow Everly").split(),
            "sector": ("Logistics Analytics Robotics Dynamics Systems Solutions Labs Technologies "
                       "Partners Holdings Capital Ventures Industries Manufacturing Foods Energy "
                       "Health Digital Networks Materials Instruments Bioscience Automotive "
                       "Aerospace Maritime Agritech Textiles Chemicals Pharma Insurance").split(),
            "suffix": {"Inc.": .22, "LLC": .20, "Ltd": .18, "GmbH": .07, "PLC": .06,
                       "Corp.": .09, "S.A.": .05, "Pty Ltd": .04, "": .09},
        },
        patterns=[("{root} {sector} {suffix}", 0.70), ("{root} & {root2} {suffix}", 0.12),
                  ("{root} {sector}", 0.18)],
        distinct_slots=[["root", "root2"]],
        rows_per_distinct=6.0,   # a customer base has repeat vendors
    )

    vessel = LexiconSpec(
        name="vessel_name",
        description="Prefix, root and element, as commercial shipping actually names hulls.",
        head=["Ever Given", "Emma Maersk", "Queen Mary 2", "MSC Oscar"],
        head_share=0.04,
        slots={
            "prefix": {"MV": .40, "MS": .21, "MT": .14, "SS": .10, "RV": .08, "HMS": .07},
            "root": ("Ocean Pacific Atlantic Northern Southern Coral Amber Crystal Golden Silver "
                     "Iron Meridian Polar Baltic Aegean Nordic Celtic Andaman Bengal Arabian "
                     "Caspian Adriatic Star Sea Cape Bay Gulf Delta Horizon Aurora Zenith Falcon "
                     "Condor Osprey Albatross Tern Petrel").split(),
            "element": ("Trader Voyager Pioneer Endeavour Spirit Explorer Mariner Navigator "
                        "Carrier Express Runner Sentinel Guardian Harmony Venture Enterprise "
                        "Ranger Courier Provider Sovereign Empress Princess Monarch Ambassador "
                        "Challenger Discoverer").split(),
            "suffix": {"": .86, " II": .06, " III": .03, " Express": .03, " Star": .02},
        },
        patterns=[("{prefix} {root} {element}{suffix}", 0.76), ("{root} {element}{suffix}", 0.24)],
        rows_per_distinct=4.0,   # a fleet calls at a port repeatedly
    )

    procedure = LexiconSpec(
        name="medical_procedure",
        description="Approach, site and action. head_share is high because clinical coding "
                    "genuinely concentrates on a handful of common procedures.",
        head=["Appendectomy", "Cholecystectomy", "Coronary artery bypass graft",
              "Total knee arthroplasty", "Cataract extraction", "Caesarean section",
              "Colonoscopy", "Tonsillectomy", "Hernia repair", "Cardiac catheterisation"],
        head_share=0.30,
        slots={
            "approach": {"Laparoscopic": .26, "Open": .21, "Percutaneous": .16, "Endoscopic": .14,
                         "Robotic-assisted": .09, "Transcatheter": .07, "Arthroscopic": .07},
            "site": ("gastric hepatic renal cardiac pulmonary thoracic abdominal inguinal femoral "
                     "cervical lumbar cranial ophthalmic nasal dental vascular biliary splenic "
                     "pancreatic colonic rectal prostatic uterine ovarian thyroid").split(),
            "action": ("resection repair reconstruction excision biopsy drainage ablation bypass "
                       "decompression fixation replacement revision exploration dilation "
                       "stenting fusion release").split(),
            "laterality": {"": .70, ", left": .15, ", right": .15},
        },
        patterns=[("{approach} {site} {action}{laterality}", 0.68),
                  ("{site} {action}{laterality}", 0.32)],
        rows_per_distinct=40.0,  # coding concentrates hard on common procedures
    )

    return {s.name: s for s in (person, company, vessel, procedure)}


_BUILTINS: Optional[Dict[str, LexiconSpec]] = None


def builtin_specs() -> Dict[str, LexiconSpec]:
    """Built-in lexicons, built once."""
    global _BUILTINS
    if _BUILTINS is None:
        _BUILTINS = _build_builtins()
    return _BUILTINS


def get_spec(name: str) -> Optional[LexiconSpec]:
    return builtin_specs().get(name)
