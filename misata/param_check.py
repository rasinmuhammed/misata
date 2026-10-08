"""Strict checks for numeric distribution parameters.

The numeric generator falls through to ``uniform(0, 1000)`` for any
distribution name it does not recognise, and reads parameters with defaults,
so ``distribution: "gumbel"`` or ``lamda: 3`` used to produce a column of
plausible-looking numbers that matched nothing the schema said. A declaration
language whose typos silently succeed cannot promise that what you declare
holds. This module makes those cases errors, with a suggestion, at the moment
the column is built:

- an unknown distribution name raises, naming the closest supported one;
- a parameter that is a near-miss of one the distribution reads (``lamda``,
  ``sigm``, ``mena``) raises, unless the intended key is also present;
- values the sampler cannot honour (negative spread, ``min > max``, a
  probability outside 0..1) raise.

Unrecognised keys that are not near-misses are left alone: parameters carry
many cross-cutting options (``decimals``, ``rollup``, ``anomaly_rate`` and
dozens more) that are not distribution parameters.
"""
from __future__ import annotations

import difflib
import warnings
from typing import Any, Dict, Optional

# The parameters each sampler reads (see DataSimulator.generate_column).
DIST_PARAMS: Dict[str, frozenset] = {
    "normal": frozenset({"mean", "std"}),
    "lognormal": frozenset({"mu", "sigma", "mean", "std"}),
    "power_law": frozenset({"alpha", "a", "scale"}),
    "uniform": frozenset({"min", "max"}),
    "poisson": frozenset({"lambda"}),
    "binomial": frozenset({"n", "p"}),
    "exponential": frozenset({"scale"}),
    "gamma": frozenset({"shape", "scale"}),
    "beta": frozenset({"a", "b"}),
    "empirical": frozenset({"quantiles"}),
    "categorical": frozenset({"choices", "probabilities"}),
    "sequence": frozenset({"start"}),
    # Studio's histogram inference emits this; generation treats it as its
    # declared min/max range.
    "custom": frozenset({"control_points"}),
}
_SAME_AS = {"log_normal": "lognormal", "pareto": "power_law", "zipf": "power_law"}
_ALIASES = {
    "gaussian": "normal", "gauss": "normal", "norm": "normal",
    "log-normal": "lognormal", "log normal": "lognormal", "lognorm": "lognormal",
    "power-law": "power_law", "powerlaw": "power_law", "power law": "power_law",
    "exp": "exponential",
}
# Supported per column type. Discrete samplers (poisson, binomial) are
# int-only; float columns have no sampler for them.
_FLOAT_DISTS = {"normal", "lognormal", "log_normal", "power_law", "pareto", "zipf",
                "uniform", "exponential", "gamma", "beta", "empirical", "categorical",
                "sequence", "custom"}
_INT_DISTS = _FLOAT_DISTS | {"poisson", "binomial"}
_ALL_DIST_KEYS = frozenset().union(*DIST_PARAMS.values())


class DistributionParamError(ValueError):
    """A numeric column's distribution parameters cannot mean what they say."""


def _supported(col_type: str) -> set:
    return _INT_DISTS if col_type == "int" else _FLOAT_DISTS


def _where(column_name: Optional[str]) -> str:
    return f"column '{column_name}'" if column_name else "column"


def canonical_distribution(name: Any, col_type: str,
                           column_name: Optional[str] = None) -> str:
    """Return the canonical spelling of a distribution name, or raise."""
    if not isinstance(name, str):
        raise DistributionParamError(
            f"{_where(column_name)}: distribution must be a name, got {name!r}")
    key = name.strip().lower()
    key = _ALIASES.get(key, key)
    supported = _supported(col_type)
    if key in supported:
        return key
    options = sorted(supported)
    hint = difflib.get_close_matches(key, options, n=1, cutoff=0.6)
    other = _INT_DISTS - _FLOAT_DISTS if col_type == "float" else set()
    msg = f"{_where(column_name)} ({col_type}): unknown distribution {name!r}"
    if key in other:
        msg += f" ('{key}' is a count distribution, available on int columns)"
    elif hint:
        msg += f" (did you mean {hint[0]!r}?)"
    raise DistributionParamError(msg + f". Supported: {', '.join(options)}.")


def check_distribution_params(col_type: str, params: Dict[str, Any],
                              column_name: Optional[str] = None) -> Dict[str, Any]:
    """Validate an int/float column's params. Returns them with the
    distribution name canonicalised; raises :class:`DistributionParamError`."""
    if col_type not in ("int", "float") or "distribution" not in params:
        return params
    if params.get("_distribution_is_default"):
        dist = "normal"
    else:
        dist = canonical_distribution(params["distribution"], col_type, column_name)
        params = {**params, "distribution": dist}
    reads = DIST_PARAMS[_SAME_AS.get(dist, dist)] | {"min", "max"}
    where = _where(column_name)

    for k in params:
        if k in _ALL_DIST_KEYS or k in reads or not isinstance(k, str) or k.startswith("_"):
            continue
        near = difflib.get_close_matches(k.lower(), sorted(reads), n=1, cutoff=0.75)
        if near and near[0] not in params:
            raise DistributionParamError(
                f"{where}: unknown parameter {k!r} for {dist}; did you mean "
                f"{near[0]!r}? {dist} reads: {', '.join(sorted(reads))}.")

    def num(key: str) -> Optional[float]:
        v = params.get(key)
        if v is None or isinstance(v, bool):
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None  # "@parent.x" references and similar resolve later

    lo, hi = num("min"), num("max")
    if lo is not None and hi is not None and lo > hi:
        raise DistributionParamError(f"{where}: min ({lo:g}) is greater than max ({hi:g})")
    for key in ("std", "sigma", "scale"):
        v = num(key)
        if v is not None and v < 0:
            raise DistributionParamError(f"{where}: {key} must be >= 0, got {v:g}")
    if dist in ("power_law", "pareto", "zipf"):
        a = num("alpha") if "alpha" in params else num("a")
        if a is not None and a <= 0:
            raise DistributionParamError(f"{where}: alpha must be > 0, got {a:g}")
    if dist == "gamma":
        v = num("shape")
        if v is not None and v <= 0:
            raise DistributionParamError(f"{where}: gamma shape must be > 0, got {v:g}")
    if dist == "beta":
        for key in ("a", "b"):
            v = num(key)
            if v is not None and v <= 0:
                raise DistributionParamError(f"{where}: beta {key} must be > 0, got {v:g}")
    if dist == "poisson":
        v = num("lambda")
        if v is not None and v < 0:
            raise DistributionParamError(f"{where}: lambda must be >= 0, got {v:g}")
    if dist == "binomial":
        p, n = num("p"), num("n")
        if p is not None and not 0 <= p <= 1:
            raise DistributionParamError(f"{where}: binomial p must be in [0, 1], got {p:g}")
        if n is not None and (n < 0 or n != int(n)):
            raise DistributionParamError(
                f"{where}: binomial n must be a non-negative integer, got {n:g}")
    return params


def repair_distribution_params(col_type: str, params: Dict[str, Any],
                               column_name: Optional[str] = None) -> Dict[str, Any]:
    """For machine-written schemas (LLM output): instead of raising, drop what
    cannot be honoured, with a warning, so one bad column does not sink the
    whole parse."""
    try:
        return check_distribution_params(col_type, params, column_name)
    except DistributionParamError as e:
        warnings.warn(f"{e} Falling back to the column's default distribution.",
                      UserWarning, stacklevel=2)
        keep = {k: v for k, v in params.items()
                if k not in _ALL_DIST_KEYS - {"min", "max", "choices", "probabilities"}
                and k != "distribution"}
        lo, hi = keep.get("min"), keep.get("max")
        try:
            if lo is not None and hi is not None and float(lo) > float(hi):
                keep["min"], keep["max"] = hi, lo
        except (TypeError, ValueError):
            pass
        keep["distribution"] = "normal"
        keep["_distribution_is_default"] = True
        return keep
