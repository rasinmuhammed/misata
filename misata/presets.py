"""Use-case presets: one word that sets the realism knobs a use case needs.

"Realistic" means different things to different jobs. A sales demo wants
clean, current-looking data; a unit test wants small, fixed fixtures; a load
test wants volume and skew; an ML pipeline wants the dirt it will meet in
production; an agent evaluation wants current dates and a known amount of
mess. A single default disappoints at least one of them, so name the job::

    misata.generate_from_schema(schema, preset="demo")
    misata generate --config misata.yaml --preset load --rows 1000000

or in the schema itself (``preset: ml`` in YAML, ``"__preset__": "ml"`` in a
dict). Declarations always win: a preset only fills in what the schema did not
say, and never edits a declared outcome.

=========  ===========================================================
``demo``   dates end today, coherence repairs on, no deliberate mess
``test``   small tables (<= 200 rows), seed 0 when unset, no mess
``load``   rows x 10 (``scale``), expensive coherence passes off
``ml``     ~3% nulls, 1% outliers, typos, duplicates (keys protected),
           correlations inferred from column names
``eval``   ``demo`` dates plus modest mess (2% nulls, typos, duplicates)
=========  ===========================================================
"""
from __future__ import annotations

import copy
from typing import Any, Dict, Optional

PRESETS: Dict[str, str] = {
    "demo": "dates end today, coherence repairs on, no deliberate mess",
    "test": "small tables (<= 200 rows), a fixed seed, no mess",
    "load": "rows scaled up (x10 by default), expensive coherence passes off",
    "ml": "declared nulls, outliers, typos and duplicates, inferred correlations",
    "eval": "current dates plus modest mess, for agent and text-to-SQL evaluation",
}


def _key_columns(schema) -> list:
    keys = set()
    for t, cols in (schema.columns or {}).items():
        for c in cols:
            if c.unique or c.type == "foreign_key":
                keys.add(c.name)
    for r in schema.relationships or []:
        keys.update((r.parent_key, r.child_key))
    return sorted(keys)


def _anchor_dates_to_today(schema, today=None) -> bool:
    """Shift every declared date/datetime range so the latest one ends today,
    keeping each span. Skipped when curves or processes carry their own dates,
    because moving the columns without them would break the declaration."""
    import pandas as pd

    if (schema.outcome_curves or schema.rate_curves
            or getattr(schema, "processes", None)):
        return False
    ends = []
    for cols in (schema.columns or {}).values():
        for c in cols:
            p = c.distribution_params or {}
            if c.type in ("date", "datetime") and p.get("end"):
                try:
                    ends.append(pd.Timestamp(p["end"]))
                except (TypeError, ValueError):
                    pass
    if not ends:
        return False
    today = pd.Timestamp(today or pd.Timestamp.now()).normalize()
    shift = today - max(ends)
    if shift <= pd.Timedelta(0):
        return False
    shift = pd.Timedelta(days=shift.days)
    for cols in (schema.columns or {}).values():
        for c in cols:
            p = c.distribution_params or {}
            if c.type not in ("date", "datetime"):
                continue
            for k in ("start", "end"):
                if p.get(k):
                    try:
                        p[k] = str((pd.Timestamp(p[k]) + shift).date())
                    except (TypeError, ValueError):
                        pass
    return True


def apply_preset(schema, name: str, *, scale: Optional[float] = None,
                 today: Any = None):
    """A copy of ``schema`` with the preset's defaults filled in."""
    from misata.schema import NoiseConfig, RealismConfig

    key = str(name).strip().lower()
    if key not in PRESETS:
        import difflib
        hint = difflib.get_close_matches(key, list(PRESETS), n=1)
        raise ValueError(f"unknown preset {name!r}"
                         + (f" (did you mean {hint[0]!r}?)" if hint else "")
                         + f"; choose from {', '.join(PRESETS)}")
    s = copy.deepcopy(schema)
    if s.realism is None:
        object.__setattr__(s, "realism", RealismConfig())

    if key in ("demo", "eval"):
        _anchor_dates_to_today(s, today)
        if s.realism.coherence == "off":
            s.realism.coherence = "standard"
    if key == "test":
        for t in s.tables:
            t.row_count = min(t.row_count, 200)
        if s.seed is None:
            s.seed = 0
    if key == "load":
        factor = float(scale if scale is not None else 10)
        for t in s.tables:
            t.row_count = max(1, int(round(t.row_count * factor)))
        s.realism.coherence = "off"
    if key in ("ml", "eval") and s.noise_config is None:
        rates = ({"null_rate": 0.03, "outlier_rate": 0.01, "typo_rate": 0.005,
                  "duplicate_rate": 0.002} if key == "ml" else
                 {"null_rate": 0.02, "outlier_rate": 0.0, "typo_rate": 0.005,
                  "duplicate_rate": 0.003})
        s.noise_config = NoiseConfig(mode="analytics_safe" if key == "eval" else "ml_training",
                                     protected_columns=_key_columns(s), **rates)
    if key == "ml":
        from misata import _infer_correlations
        _infer_correlations(s)
    object.__setattr__(s, "preset", None)   # applied; never twice
    return s
