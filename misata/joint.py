"""Joint satisfaction: several declared margins holding at once, exactly.

Today a schema can declare "40% enterprise" and "March revenue is 300,000" and
get both. What it cannot declare is how those two relate: that enterprise
accounts churn at three times the rate of starter, that APAC skews to annual
billing. Declare two margins over the same rows and you get whatever
independence the sampler happens to produce, which is a specification nobody
wrote.

The classical answer is Iterative Proportional Fitting (Deming and Stephan,
1940), and it has a property worth stating precisely because it is the reason
to prefer it over anything newer: **IPF converges to the unique maximum-entropy
distribution consistent with the declared margins.** Not a distribution that
fits. The provably least-assuming one. When a user states margins and nothing
else, max-entropy is the principled answer to everything they did not state.

The synthetic-population literature runs IPF against a seed matrix taken from
real microdata, and concedes its methods "lack formal optimality guarantees".
This has no microdata and wants none: a uniform seed IS the max-entropy prior,
which makes the declaration-only case cleaner than the case that field
struggles with.

Two things then have to be true for the result to be a guarantee rather than a
tendency:

* **Convergence is decidable in advance.** IPF converges exactly when the
  declared margins admit a joint distribution at all, and the conditions are
  known. Margins that contradict each other are refused with the arithmetic
  before generation, never approximated during it.
* **Rounding preserves the margins.** IPF returns real numbers; rows are
  integers. For a two-way table the rounding problem is a transportation
  problem whose constraint matrix is totally unimodular, so an integer
  solution matching every margin exactly always exists and is found here. For
  three-way and above no such guarantee exists in general, and this says so
  rather than pretending.
"""
from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np


class MarginsIncompatible(ValueError):
    """Declared margins admit no joint distribution, with the arithmetic."""


def _normalise(margin: Dict[str, float]) -> Tuple[List[str], np.ndarray]:
    keys = list(margin)
    v = np.asarray([float(margin[k]) for k in keys], dtype=float)
    if (v < 0).any():
        raise MarginsIncompatible(f"negative share in margin: {margin}")
    s = v.sum()
    if s <= 0:
        raise MarginsIncompatible(f"margin sums to {s}: {margin}")
    return keys, v / s


def check_margins(margins: Dict[str, Dict[str, float]]) -> None:
    """Refuse margins that cannot describe one population.

    Every margin is a view of the SAME rows, so each must account for all of
    them. A margin summing to 0.9 is not a rounding slip, it is a fifth of a
    population left undescribed, and guessing where it went is precisely the
    substitution this engine refuses to make.
    """
    for name, m in margins.items():
        if not m:
            raise MarginsIncompatible(f"margin '{name}' is empty")
        total = sum(float(v) for v in m.values())
        if abs(total - 1.0) > 1e-6:
            raise MarginsIncompatible(
                f"margin '{name}' sums to {total:.6f}, not 1.0. Every margin "
                f"describes all the same rows, so each must account for all of "
                f"them; rescale it or add the missing category.")


def ipf(
    margins: Dict[str, Dict[str, float]],
    seed: Optional[np.ndarray] = None,
    *,
    max_iter: int = 500,
    tol: float = 1e-10,
) -> Tuple[np.ndarray, List[str], List[List[str]], Dict[str, float]]:
    """Maximum-entropy joint distribution matching every declared margin.

    Args:
        margins: dimension name -> {category: share}, each summing to 1.
        seed: Optional prior over cells. Uniform (the max-entropy prior) when
            omitted. A zero in the seed is a structural zero: a cell declared
            impossible, which IPF preserves.
        max_iter: Iteration ceiling.
        tol: Convergence threshold on the largest margin error.

    Returns:
        (table, dims, levels, diagnostics) where `table` sums to 1.

    Raises:
        MarginsIncompatible: margins that admit no joint distribution.
    """
    check_margins(margins)
    dims = list(margins)
    levels, targets = [], []
    for d in dims:
        k, v = _normalise(margins[d])
        levels.append(k)
        targets.append(v)

    shape = tuple(len(k) for k in levels)
    table = np.ones(shape, dtype=float) if seed is None else np.asarray(seed, dtype=float).copy()
    if table.shape != shape:
        raise MarginsIncompatible(
            f"seed shape {table.shape} does not match declared margins {shape}")
    if (table < 0).any():
        raise MarginsIncompatible("seed contains a negative cell")
    if table.sum() <= 0:
        raise MarginsIncompatible("seed is empty; every cell is a structural zero")
    table /= table.sum()

    worst = float("inf")
    for it in range(max_iter):
        for axis, target in enumerate(targets):
            cur = table.sum(axis=tuple(a for a in range(table.ndim) if a != axis))
            # A structural zero makes a margin unreachable: no mass can ever
            # arrive in a cell declared impossible.
            dead = (cur <= 0) & (target > 0)
            if dead.any():
                bad = [levels[axis][i] for i in np.nonzero(dead)[0]]
                raise MarginsIncompatible(
                    f"margin '{dims[axis]}' requires mass in {bad}, but every "
                    f"cell reaching those categories is a structural zero in "
                    f"the seed, so no joint distribution can satisfy it.")
            scale = np.divide(target, cur, out=np.ones_like(cur), where=cur > 0)
            table *= scale.reshape([-1 if a == axis else 1 for a in range(table.ndim)])
        worst = max(
            float(np.abs(table.sum(axis=tuple(a for a in range(table.ndim) if a != ax)) - tg).max())
            for ax, tg in enumerate(targets))
        if worst < tol:
            return table, dims, levels, {"iterations": it + 1, "max_margin_error": worst}

    raise MarginsIncompatible(
        f"IPF did not converge in {max_iter} iterations; largest margin error "
        f"{worst:.3g}. Declared margins that cannot be met together look like "
        f"this, and continuing would substitute a specification nobody wrote.")


def integerise_2d(table: np.ndarray, n: int) -> np.ndarray:
    """Round a two-way table to integers preserving BOTH margins exactly.

    Flooring alone loses rows, and largest-remainder over all cells hits the
    grand total while breaking the row and column totals it was supposed to
    respect. For two dimensions the rounding problem is a transportation
    problem with a totally unimodular constraint matrix, so an integer
    solution matching every margin exactly is guaranteed to exist; this finds
    one by assigning each margin's rounded deficit greedily by fractional part.
    """
    if table.ndim != 2:
        raise ValueError("integerise_2d expects a two-way table")
    exact = table * n
    out = np.floor(exact).astype(np.int64)
    frac = exact - out

    row_t = _largest_remainder(exact.sum(axis=1), n)
    col_t = _largest_remainder(exact.sum(axis=0), n)
    row_need = row_t - out.sum(axis=1)
    col_need = col_t - out.sum(axis=0)

    # Hand out one unit at a time to the cell with the largest fractional part
    # among those whose row AND column both still want one.
    order = np.dstack(np.unravel_index(np.argsort(-frac, axis=None), frac.shape))[0]
    for i, j in order:
        if row_need[i] > 0 and col_need[j] > 0:
            out[i, j] += 1
            row_need[i] -= 1
            col_need[j] -= 1
        if not (row_need > 0).any():
            break
    # Any residue is a genuine integrality conflict, not a silent nudge.
    if row_need.any() or col_need.any():
        warnings.warn(
            f"integerise_2d: {int(np.abs(row_need).sum())} unit(s) could not be "
            f"placed without breaking a margin; the table is reported as is.")
    return out


def _largest_remainder(values: np.ndarray, total: int) -> np.ndarray:
    """Round to integers summing to exactly `total`."""
    v = np.asarray(values, dtype=float)
    s = v.sum()
    scaled = v * (total / s) if s > 0 else np.zeros_like(v)
    base = np.floor(scaled).astype(np.int64)
    rem = int(total - base.sum())
    if rem > 0:
        for i in np.argsort(-(scaled - base))[:rem]:
            base[i] += 1
    return base


def integerise_nd(table: np.ndarray, n: int) -> np.ndarray:
    """Round an N-way table to integers summing to exactly `n`.

    The grand total is exact. Individual margins are NOT guaranteed beyond two
    dimensions, because the totally-unimodular argument that makes two-way
    controlled rounding always solvable does not extend, and no algorithm can
    promise what does not always exist. Callers get the residual reported
    rather than a claim.
    """
    flat = _largest_remainder(np.asarray(table, dtype=float).ravel(), n)
    return flat.reshape(table.shape)


def solve_joint(
    margins: Dict[str, Dict[str, float]],
    n_rows: int,
    *,
    seed_weights: Optional[Dict[Tuple[str, ...], float]] = None,
    forbidden: Optional[Sequence[Dict[str, str]]] = None,
) -> Tuple[np.ndarray, List[str], List[List[str]], Dict[str, object]]:
    """Declared margins to an exact integer cell table over `n_rows` rows.

    Args:
        margins: column -> {value: share}. Each must sum to 1.
        n_rows: Rows the table must account for, exactly.
        seed_weights: Cell emphasis, keyed by the tuple of category values.
            A weight above 1 pulls mass toward that combination; the margins
            still hold. This is how a dependency is declared without stating
            a whole joint distribution by hand.
        forbidden: Combinations declared impossible. Structural zeros.

    Returns:
        (counts, dims, levels, diagnostics). `counts` sums to `n_rows`.
    """
    dims = list(margins)
    levels = [list(margins[d]) for d in dims]
    index = {d: {v: i for i, v in enumerate(levels[k])} for k, d in enumerate(dims)}
    shape = tuple(len(v) for v in levels)

    seed = np.ones(shape, dtype=float)
    for combo in (forbidden or []):
        try:
            seed[tuple(index[d][combo[d]] for d in dims)] = 0.0
        except KeyError as e:
            raise MarginsIncompatible(
                f"forbidden combination {combo} names {e} which is not a "
                f"declared category") from None
    for combo, w in (seed_weights or {}).items():
        seed[tuple(index[d][c] for d, c in zip(dims, combo))] = float(w)

    table, dims, levels, diag = ipf(margins, seed=seed)
    if len(dims) == 2:
        counts = integerise_2d(table, n_rows)
        diag["margins_exact"] = True
    else:
        counts = integerise_nd(table, n_rows)
        diag["margins_exact"] = False
        diag["note"] = ("grand total exact; per-margin integer exactness is not "
                        "guaranteed above two dimensions")
    diag["cells"] = int(counts.size)
    diag["n_rows"] = int(counts.sum())
    return counts, dims, levels, diag


def assign_rows(
    counts: np.ndarray,
    dims: Sequence[str],
    levels: Sequence[Sequence[str]],
    rng: np.random.Generator,
) -> Dict[str, np.ndarray]:
    """Expand a cell table into per-column value arrays, then shuffle jointly.

    The realised counts equal the solved counts exactly, because the rows ARE
    the cell table expanded. Nothing is sampled and hoped for.
    """
    cols: Dict[str, List[str]] = {d: [] for d in dims}
    for idx in np.ndindex(counts.shape):
        c = int(counts[idx])
        if not c:
            continue
        for k, d in enumerate(dims):
            cols[d].extend([levels[k][idx[k]]] * c)
    order = rng.permutation(int(counts.sum()))
    return {d: np.asarray(v, dtype=object)[order] for d, v in cols.items()}


def apply_joint_distributions(tables, config, rng) -> None:
    """Overwrite declared columns so the emitted rows match every margin.

    Runs after generation. The rows ARE the solved cell table expanded and
    shuffled, so the realised counts equal the declared ones by construction
    rather than by sampling and hoping.
    """
    for spec in (getattr(config, "joint_distributions", None) or []):
        df = tables.get(spec.table)
        if df is None or df.empty:
            continue
        missing = [c for c in spec.margins if c not in df.columns]
        if missing:
            warnings.warn(
                f"JointDistribution '{spec.name}': {spec.table} has no column(s) "
                f"{missing}. Skipping.")
            continue
        dims = list(spec.margins)
        weights = {}
        for key, w in (spec.emphasis or {}).items():
            combo = tuple(key.split("|"))
            if len(combo) != len(dims):
                warnings.warn(
                    f"JointDistribution '{spec.name}': emphasis key {key!r} has "
                    f"{len(combo)} parts but {len(dims)} margins are declared. "
                    f"Ignoring it.")
                continue
            weights[combo] = float(w)
        counts, dims, levels, _diag = solve_joint(
            spec.margins, len(df), seed_weights=weights or None,
            forbidden=spec.forbidden or None)
        for col, values in assign_rows(counts, dims, levels, rng).items():
            df[col] = values
        tables[spec.table] = df
