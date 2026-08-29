"""Units that wear out, with an exact remaining-useful-life label.

Every other primitive in Misata draws each row independently. That is right for
orders and payments and wrong for equipment, because a machine has a history:
wear accumulates, measurements drift, and eventually it fails.

The public predictive-maintenance datasets mostly do not have this. In AI4I
2020, the most widely used one, tool wear is as likely to fall as to rise
between consecutive readings for the same machine, and there is no
remaining-life label at all. A dataset for *predicting* failure in which nothing
progresses toward failure is a classification exercise wearing a prognostics
costume.

What is declared here is the failure time. Each unit draws a life, damage
accumulates toward it, and the sensors follow the damage. So remaining useful
life is exact by construction rather than annotated afterwards, which is the
property that makes the label worth training on and the reason this belongs in a
declarative engine rather than a simulator.

Two layers, kept deliberately separate because they carry different weight:

  * The trajectory. Damage, remaining life, and how a measurement responds to
    damage. Shapes are stated by the user; nothing here claims to be any
    particular machine.

  * The bearing physics in `defect_frequencies`, which is not a shape anyone
    chose. A rolling-element bearing's fault frequencies follow from its
    geometry and shaft speed, and the standard diagnostic method recovers them
    from the vibration. Those formulas are textbook and checkable.

What this is not: a validated model of a specific bearing, spindle or pump. The
damage law is a simplified lumped model. Anything published from it should say
so, and should rest its claims on the labels being exact rather than on the
physics being faithful.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from misata.schema import Degradation, FailureMode, SensorResponse


# --------------------------------------------------------------------------- #
# Bearing physics: geometry in, frequencies out. Nothing is fitted.
# --------------------------------------------------------------------------- #

def defect_frequencies(
    rpm: float,
    n_elements: int = 9,
    ball_diameter: float = 0.3126,
    pitch_diameter: float = 1.537,
    contact_angle_deg: float = 0.0,
) -> Dict[str, float]:
    """The four characteristic fault frequencies of a rolling-element bearing.

    A localised defect is struck once per rolling element that passes it, so a
    damaged bearing rings at a rate fixed by geometry and shaft speed::

        BPFO = (N*n/2) * (1 - (Bd/Pd) cos B)      outer race
        BPFI = (N*n/2) * (1 + (Bd/Pd) cos B)      inner race
        BSF  = (Pd*n/(2 Bd)) * (1 - ((Bd/Pd) cos B)^2)   rolling element
        FTF  = (n/2) * (1 - (Bd/Pd) cos B)        cage

    Defaults are the SKF 6205-2RS deep-groove ball bearing, the one on the Case
    Western Reserve test rig, so the output is checkable against published
    values: at 1797 rpm this returns BPFO 107.36 Hz.

    Args:
        rpm: Shaft speed.
        n_elements: Number of balls or rollers.
        ball_diameter: Rolling element diameter, any unit.
        pitch_diameter: Pitch circle diameter, same unit as ball_diameter.
        contact_angle_deg: 0 for a radial ball bearing.

    Returns:
        Frequencies in Hz, keyed ``shaft``, ``BPFO``, ``BPFI``, ``BSF``, ``FTF``.
    """
    if pitch_diameter <= 0 or ball_diameter <= 0:
        raise ValueError("ball_diameter and pitch_diameter must be positive")
    if n_elements < 1:
        raise ValueError("a bearing has at least one rolling element")

    n = rpm / 60.0
    ratio = (ball_diameter / pitch_diameter) * math.cos(math.radians(contact_angle_deg))
    return {
        "shaft": n,
        "BPFO": (n_elements * n / 2.0) * (1.0 - ratio),
        "BPFI": (n_elements * n / 2.0) * (1.0 + ratio),
        "BSF": (pitch_diameter * n / (2.0 * ball_diameter)) * (1.0 - ratio ** 2),
        "FTF": (n / 2.0) * (1.0 - ratio),
    }


# --------------------------------------------------------------------------- #
# Trajectories
# --------------------------------------------------------------------------- #

def _resolve_modes(spec: Degradation):
    """Normalise both spellings of `failure_modes` into names, weights, effects."""
    if not (spec.failure_mode_column and spec.failure_modes):
        return None, None, {}
    names, weights, effects = [], [], {}
    for name, value in spec.failure_modes.items():
        if isinstance(value, FailureMode):
            names.append(name)
            weights.append(float(value.weight))
            effects[name] = dict(value.accentuates)
        elif isinstance(value, dict):
            names.append(name)
            weights.append(float(value.get("weight", 1.0)))
            effects[name] = dict(value.get("accentuates", {}))
        else:
            names.append(name)
            weights.append(float(value))
            effects[name] = {}
    total = sum(weights)
    if total <= 0:
        raise ValueError("failure_modes weights must sum to more than zero")
    return names, np.array(weights) / total, effects


def _respond(damage: np.ndarray, spec: SensorResponse,
             rng: np.random.Generator, scale: float = 1.0) -> np.ndarray:
    """A measurement's value along a damage trajectory.

    `baseline` at damage 0 and `at_failure` at damage 1 in every shape, so the
    endpoints mean the same thing however the middle is drawn. Exponential is
    the one worth having: a vibration RMS sits near its healthy value for most
    of the life and then climbs steeply, which is why a health indicator looks
    flat until it does not.
    """
    if spec.shape == "linear":
        frac = damage
    elif spec.shape == "sqrt":
        frac = np.sqrt(damage)
    elif spec.shape == "exponential":
        # (e^{k d} - 1) / (e^k - 1): 0 at d=0, 1 at d=1, convex in between.
        k = 3.0
        frac = (np.exp(k * damage) - 1.0) / (math.exp(k) - 1.0)
    elif spec.shape == "kurtosis":
        # A Gamma-shaped bump peaking at damage=0.2, the "onset of defect
        # growth" stage in the bearing literature, then decaying most of the
        # way back toward baseline by failure: (d/p) * exp(1 - d/p) is 0 at
        # d=0, exactly 1 at d=p, and ~0.09 by d=1 with p=0.2. `at_failure`
        # is read as the peak value here, not the end-of-life value -- the
        # one shape where that distinction matters, because there is no
        # monotonic "value at failure" for a feature that peaks and falls.
        p = 0.2
        frac = (damage / p) * np.exp(1.0 - damage / p)
    else:  # pragma: no cover - Literal keeps this unreachable
        raise ValueError(f"unknown response shape {spec.shape!r}")

    # `scale` carries the unit's own susceptibility and the failure mode's
    # signature: how far this measurement travels for this machine.
    values = spec.baseline + (spec.at_failure - spec.baseline) * frac * scale
    if spec.noise:
        values = values + rng.normal(0.0, spec.noise, size=values.shape)
    if spec.monotonic:
        # A cumulative quantity never falls. Noise is still present, it just
        # cannot carry the series backwards: a reading is at least the highest
        # already seen, which is what an accumulating measurement does.
        values = np.maximum.accumulate(
            values if spec.at_failure >= spec.baseline else -values)
        if spec.at_failure < spec.baseline:
            values = -values
    return np.round(values, spec.decimals)


def _simulate_damage(spec: Degradation, life_nominal: float,
                      rng: np.random.Generator, unit_label: str,
                      max_cycles: int) -> tuple[np.ndarray, list[dict]]:
    """Cycle-by-cycle damage for one unit, with maintenance interventions.

    Without a maintenance_policy this reduces to the original closed form,
    (cycle/life)**exponent, computed the slow way for exactly one reason:
    a unit that is repaired needs its remaining life RE-DERIVED from where
    damage actually sits after the repair, not read off a number drawn
    before any row existed. Closed form and cycle-by-cycle agree when there
    are zero repairs; they can only differ once there is at least one.
    """
    events: list[dict] = []
    damages: list[float] = []
    effective_life = life_nominal
    t_reset = 0.0
    cycle = 0
    exponent = spec.damage_exponent

    cooldown = spec.maintenance_min_cooldown_cycles
    if cooldown is None:
        cooldown = max(3, round(0.05 * life_nominal))
    cycles_since_last_event = cooldown  # first repair is never blocked

    while cycle < max_cycles:
        cycle += 1
        t_reset += 1.0
        cycles_since_last_event += 1
        d = (t_reset / effective_life) ** exponent
        cooled_down = cycles_since_last_event >= cooldown

        fired, kind = False, None
        if (spec.maintenance_policy == "condition_based"
                and spec.maintenance_trigger_damage is not None
                and d >= spec.maintenance_trigger_damage
                and d < 1.0
                and cooled_down):
            fired, kind = True, "condition_based"
            # A technician does not arrive the instant the threshold is
            # crossed. Damage is left at its true value -- which may already
            # sit past the trigger if the unit was still in cooldown from a
            # previous visit -- not forced back down to the nominal trigger.
        elif (spec.maintenance_policy == "scheduled"
                and spec.maintenance_interval_cycles
                and t_reset >= spec.maintenance_interval_cycles
                and d < 1.0
                and cooled_down):
            fired, kind = True, "scheduled"

        if fired:
            restoration = float(np.clip(spec.maintenance_restoration, 0.0, 1.0))
            d_after = d * (1.0 - restoration)
            # The row logged for this cycle reports the reading a sensor
            # would actually show: right after the intervention, not the
            # instant before it. `d` (pre-repair) survives only inside the
            # event record, as damage_before, for anyone who wants to know
            # how close to the trigger the unit was allowed to run.
            damages.append(d_after)
            if restoration < 1.0:
                # Repeated imperfect repairs leave the unit more susceptible
                # to future deterioration -- documented in the CBM/imperfect
                # repair literature, and modelled here as a shortened
                # effective life for the segment that follows. A perfect
                # repair (restoration=1.0) does not carry this penalty,
                # matching the as-good-as-new definition.
                effective_life = effective_life * (1.0 - spec.maintenance_wear_penalty)
            t_reset = effective_life * (d_after ** (1.0 / exponent)) if d_after > 0 else 0.0
            cycles_since_last_event = 0
            events.append({
                "unit_id": unit_label, "cycle": cycle, "event_type": kind,
                "damage_before": round(d, 6), "damage_after": round(d_after, 6),
                "restoration_fraction": restoration,
            })
            continue

        if d >= 1.0:
            # The failure cycle's reading is 1.0 by definition, not whatever
            # the sampled float happened to overshoot to. With maintenance,
            # effective_life is a re-anchored float rather than the original
            # integer life, so integer-cycle sampling generically lands past
            # 1.0 rather than exactly on it -- clamp here, the same
            # guarantee the no-maintenance path gets for free from
            # `(cycle/life)**exponent` landing on exactly 1.0 at cycle=life.
            damages.append(1.0)
            break
        damages.append(d)
    else:  # pragma: no cover - guard against a pathological policy
        raise ValueError(
            f"unit {unit_label} did not reach failure within {max_cycles} "
            "cycles -- check maintenance_trigger_damage, "
            "maintenance_restoration, and maintenance_wear_penalty"
        )

    return np.array(damages), events


def generate(spec: Degradation, seed: int = 42,
             return_events: bool = False):
    """One row per unit per cycle, with exact remaining-useful-life labels.

    Row count is the sum of the drawn lives rather than a number anyone chose: a
    unit that lives 300 cycles has 300 readings, and pretending otherwise would
    mean truncating histories at an arbitrary point.

    With `return_events=True` and a `maintenance_policy` declared, also
    returns a second DataFrame: one row per intervention, with the cycle it
    happened, its type, and the damage immediately before and after. Default
    is a single DataFrame, unchanged from every version before maintenance
    existed, so existing callers see no difference.
    """
    if spec.units < 1:
        raise ValueError("a fleet has at least one unit")
    if spec.life_min < 1:
        raise ValueError("life_min must be at least 1 cycle")
    if spec.life_min > spec.life_max:
        raise ValueError(
            f"life_min ({spec.life_min}) exceeds life_max ({spec.life_max})")

    rng = np.random.default_rng(seed)

    modes, weights, effects = _resolve_modes(spec)

    frames: List[pd.DataFrame] = []
    all_events: List[dict] = []
    for unit in range(1, spec.units + 1):
        unit_label = f"U{unit:04d}"
        life_nominal = float(np.clip(rng.normal(spec.life_mean, spec.life_std),
                                      spec.life_min, spec.life_max))

        if spec.maintenance_policy is not None:
            damage, events = _simulate_damage(
                spec, life_nominal, rng, unit_label,
                max_cycles=int(spec.life_max * 20),
            )
            all_events.extend(events)
        else:
            life = int(life_nominal)
            cycles_only = np.arange(1, life + 1, dtype=int)
            # Damage is fraction of life consumed, raised to the exponent so
            # the last stretch degrades fastest. Exactly 1.0 on the final cycle.
            damage = (cycles_only / life) ** spec.damage_exponent

        life = len(damage)  # the unit's ACTUAL life, post-repair if any
        cycles = np.arange(1, life + 1, dtype=int)

        frame: Dict[str, np.ndarray] = {
            spec.unit_column: np.full(life, unit_label, dtype=object),
            spec.cycle_column: cycles,
            # Exact, because it is derived from the life this unit actually
            # had, whether that was drawn upfront or emerged from repairs.
            spec.rul_column: life - cycles,
            spec.failure_column: (cycles == life).astype(int),
        }
        if spec.damage_column:
            frame[spec.damage_column] = np.round(damage, 6)

        if spec.bearing_rpm is not None:
            unit_rpm = spec.bearing_rpm
            if spec.unit_variation:
                unit_rpm *= float(np.clip(rng.normal(1.0, spec.unit_variation), 0.5, 1.5))
            freqs = defect_frequencies(
                unit_rpm, spec.bearing_n_elements, spec.bearing_ball_diameter,
                spec.bearing_pitch_diameter, spec.bearing_contact_angle_deg,
            )
            for name, hz in freqs.items():
                frame[f"{name.lower()}_hz"] = np.full(life, round(hz, 3))

        mode = None
        if modes is not None and weights is not None:
            mode = str(rng.choice(modes, p=weights))
            frame[spec.failure_mode_column] = np.where(
                cycles == life, mode, "none")

        for response in spec.responses:
            # Two multipliers, and they mean different things. The first is this
            # unit's own susceptibility, so the fleet is a population rather
            # than one machine repeated. The second is the failure mode's
            # signature, so a heat-dissipation failure actually runs hot
            # instead of merely being labelled that way.
            scale = 1.0
            if spec.unit_variation:
                scale *= float(np.clip(
                    rng.normal(1.0, spec.unit_variation), 0.3, 2.5))
            if mode:
                scale *= float(effects.get(mode, {}).get(response.column, 1.0))
            frame[response.column] = _respond(damage, response, rng, scale)

        frames.append(pd.DataFrame(frame))

    df = pd.concat(frames, ignore_index=True)
    if return_events:
        events_df = pd.DataFrame(all_events) if all_events else pd.DataFrame(
            columns=["unit_id", "cycle", "event_type", "damage_before",
                     "damage_after", "restoration_fraction"])
        return df, events_df
    return df


# --------------------------------------------------------------------------- #
# Verification: the labels have to be checkable, not merely asserted
# --------------------------------------------------------------------------- #

def verify(df: pd.DataFrame, spec: Degradation,
           events: Optional[pd.DataFrame] = None) -> Dict[str, object]:
    """Re-derive the guarantees from the produced rows.

    An independent pass, in the same spirit as the conformance suites: the
    generator says remaining life is exact, and this recomputes it rather than
    taking its word. A declaration nobody checks is a comment.

    Pass `events` (the second return value of `generate(..., return_events=True)`)
    when a maintenance policy is declared. Without it, this function still
    checks damage is strictly increasing everywhere -- which will correctly
    FAIL on a maintenance-aware trajectory, because damage legitimately drops
    at a repair. With `events`, drops are only permitted exactly where a
    logged event says one happened, and the drop's size is cross-checked
    against that event's own damage_before/damage_after, so a repair the log
    does not know about is still caught as a real finding.
    """
    findings: List[str] = []
    units = df[spec.unit_column].nunique()

    events_by_unit: Dict[str, List[dict]] = {}
    if events is not None and len(events):
        for _, row in events.iterrows():
            events_by_unit.setdefault(row["unit_id"], []).append(row.to_dict())

    for unit, g in df.groupby(spec.unit_column, sort=False):
        g = g.sort_values(spec.cycle_column)
        life = int(g[spec.cycle_column].max())

        expected = life - g[spec.cycle_column].to_numpy()
        if not np.array_equal(expected, g[spec.rul_column].to_numpy()):
            findings.append(f"{unit}: remaining life does not equal life minus cycle")

        if int(g[spec.failure_column].sum()) != 1:
            findings.append(f"{unit}: expected exactly one failure row")
        elif int(g.loc[g[spec.failure_column] == 1, spec.rul_column].iloc[0]) != 0:
            findings.append(f"{unit}: the failure row's remaining life is not 0")

        if spec.damage_column:
            d = g[spec.damage_column].to_numpy()
            cycles = g[spec.cycle_column].to_numpy()
            repair_cycles = {e["cycle"]: e for e in events_by_unit.get(unit, [])}

            for i in range(1, len(d)):
                if d[i] > d[i - 1]:
                    continue  # normal accumulation
                # A drop is only legitimate at a logged event. The row FOR
                # the event's cycle reports the reading right after the
                # repair, so it is that row -- not the one before it -- that
                # must match damage_after exactly.
                event = repair_cycles.get(int(cycles[i]))
                if event is None:
                    findings.append(
                        f"{unit}: damage drops at cycle {cycles[i]} with no "
                        "logged maintenance event to explain it"
                    )
                elif abs(d[i] - event["damage_after"]) > 1e-4:
                    findings.append(
                        f"{unit}: cycle {cycles[i]} damage does not match "
                        "its own logged event's damage_after"
                    )

            if abs(d[-1] - 1.0) > 1e-6:
                findings.append(f"{unit}: damage does not reach 1.0 at failure")

    return {
        "units": units,
        "rows": len(df),
        "rul_exact": not findings,
        "findings": findings[:20],
        "finding_count": len(findings),
    }
