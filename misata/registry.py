"""What each declaration owes the reader, and whether it has paid.

Misata's stated rule is that a capability earns a place only if it can be
*declared* and *verified*. Measured against the code rather than the docs, 7 of
24 declarations met it: seventeen had no pre-generation refusal, five had no
post-generation audit, and ``joint_distributions`` had neither despite shipping
in 0.9.6.48. The rule was true of the design and false of a third of the
language, which is the worst of both, because nothing said so.

The failure was structural, not careless. Feasibility lives in one module and
the audit in another, each a growing pile of hand-written functions, and
nothing related the two to the list of declarations they are supposed to cover.
A new declaration could be added, wired, documented and released without either
half, and did.

This module is the join. Every declaration is listed once, with the two
obligations named, and :mod:`tests.test_declaration_contract` fails when the
registry and the code disagree. Coverage becomes a number that can only go up.

Two obligations, and what they mean:

``refusal``
    Contradictory declarations are named *before* any data exists, with the
    arithmetic shown. A generator picks one and carries on; a declarative
    engine refuses. Without this a schema that cannot hold produces data that
    quietly does not hold it.

``audit``
    The declared property is recomputed from the emitted rows, by code that
    does not share the generator's belief about what it wrote. Without this the
    guarantee is an assertion in a docstring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class Declaration:
    """One declaration and the two obligations it owes.

    Attributes:
        key: Schema-level name, as it appears in YAML. The dict form is this
            wrapped in dunders.
        summary: What the declaration states, in one line.
        refusal: Name of the feasibility check that refuses it early, or None
            while that is still owed.
        audit: ``kind`` string the coherence audit reports when the property
            does not hold on the emitted rows, or None while that is owed.
        aliases: Other spellings ``from_dict_schema`` accepts for the same
            declaration. Recorded here so the accepted vocabulary lives in one
            place: "vocabulary" and "vocabularies" both reach the same key, and
            nothing outside compat.py knew that.
        linear: Whether the declaration reduces to linear constraints over
            sufficient statistics (period sums, group sums, cell counts). These
            are the ones a single joint solve can satisfy together; the rest are
            combinatorial and are satisfied by construction. Recorded because
            the boundary is the interesting question and guessing at it is how
            declarations end up not composing.
    """

    key: str
    summary: str
    refusal: Optional[str]
    audit: Optional[str]
    linear: bool
    aliases: Tuple[str, ...] = ()

    @property
    def certified(self) -> bool:
        """Both halves present, so the docs' claim is true of this one."""
        return self.refusal is not None and self.audit is not None


#: Every schema-level declaration, once.
#:
#: ``refusal`` and ``audit`` name real symbols. A None is a debt this file
#: records rather than hides, and the contract test prints the outstanding list
#: so it stays visible in CI instead of in somebody's memory.
DECLARATIONS: Tuple[Declaration, ...] = (
    # ── exact aggregates: linear in (row count, measure sum) per cell ──
    # Not _check_curve_bounds: that one is deliberately unregistered, because
    # an unreachable period target keeps the aggregate and reports the
    # sacrifice rather than refusing. See the note in feasibility.py.
    Declaration("outcome_curves", "An aggregate over time, hit exactly.",
                "_check_curve_point_shape", "rollup_mismatch", linear=True),
    Declaration("rate_curves", "A rate over time, hit exactly.",
                None, None, linear=True),
    Declaration("group_shares", "Exact shares of a measure across a category.",
                "_check_group_shares", "group_share_mismatch", linear=True),
    Declaration("joint_distributions", "Several margins holding at once.",
                "_check_joint_margins", "joint_margin_mismatch", linear=True),
    Declaration("waterfalls", "Movements reconciling to declared balances.",
                None, "waterfall_mismatch", linear=True),
    Declaration("stock_flows", "closing = opening + received - shipped, per unit.",
                None, "stock_flow_arithmetic", linear=True),
    Declaration("constraints", "Row-level bounds, inequalities and uniqueness.",
                "_check_numeric_ranges", "when_then_violation", linear=True),
    Declaration("missingness", "Why values are missing, conditionally.",
                "_check_declared_fractions", "missingness_mismatch", linear=True),
    Declaration("duplicates", "Exactly this many duplicate rows.",
                "_check_injected_counts", "duplicate_count", linear=True),
    Declaration("typos", "Exactly this many corrupted values.",
                "_check_injected_counts", "typo_count", linear=True),
    Declaration("outliers", "Declared outliers, at a stated count.",
                "_check_injected_counts", "outlier_count", linear=True),
    Declaration("retention", "A cohort curve the cohort table shows.",
                "_check_retention_budget", "retention_mismatch", linear=True),

    # ── structure and state: combinatorial, satisfied by construction ──
    Declaration("dag_edges", "An edge table with no cycles.",
                None, "dag_cycle", linear=False),
    Declaration("closures", "A closure table equal to its edges' closure.",
                None, "closure_mismatch", linear=False),
    Declaration("graph_motifs", "Declared subgraph patterns, at an exact mix.",
                "_check_graph_motifs", "motif_background_cycle", linear=False),
    Declaration("lifecycles", "A state machine, with legal transitions.",
                "_check_lifecycles", "lifecycle_illegal_state", linear=False),
    Declaration("event_logs", "A log agreeing with the status column.",
                "_check_event_log_capacity", "event_log", linear=False),
    Declaration("bitemporal", "Two independent time axes.",
                None, "bitemporal", linear=False),
    Declaration("events", "Occurrences over a time axis.",
                "_check_temporal_eligibility", "temporal_causality", linear=False),
    Declaration("time_grids", "Timestamps on a declared grid, in declared hours.",
                None, "time_grid", linear=False),
    Declaration("late_arrivals", "Events landing after the fact.",
                "_check_declared_fractions", "late_arrival_mismatch", linear=False),
    Declaration("degradations", "Units wearing out, and when.",
                None, None, linear=False),

    # ── realism: shapes values, declares no arithmetic anyone can check ──
    Declaration("vocabularies", "Value pools for a column.",
                "_check_lexicon_capacity", None, linear=False,
                aliases=("vocabulary",)),
    Declaration("noise", "Measurement noise on a numeric column.",
                None, None, linear=False),
)

BY_KEY: Dict[str, Declaration] = {d.key: d for d in DECLARATIONS}

#: Every spelling the engine accepts, including aliases.
ACCEPTED_KEYS = frozenset(
    [d.key for d in DECLARATIONS] + [a for d in DECLARATIONS for a in d.aliases]
)


def uncertified() -> Tuple[Declaration, ...]:
    """Declarations still owing a refusal, an audit, or both."""
    return tuple(d for d in DECLARATIONS if not d.certified)


def coverage() -> Tuple[int, int]:
    """(certified, total). The number the contract test holds a floor under."""
    return sum(1 for d in DECLARATIONS if d.certified), len(DECLARATIONS)


def linear_core() -> Tuple[Declaration, ...]:
    """The declarations one joint solve could satisfy together.

    Each of these is a linear constraint over the same vector: per (table,
    period, group) cell, a row count and a measure sum. An outcome curve fixes
    the sum over a period, a group share fixes the sum over a group, a rate
    curve fixes a ratio of counts, a stock flow chains counts across periods.
    Solving them separately, in passes, is why they can silently undo one
    another; solving them together is one linear program.
    """
    return tuple(d for d in DECLARATIONS if d.linear)
