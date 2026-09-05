"""Every declaration owes a refusal and an audit, and the registry must be true.

Misata's stated rule is that a capability earns a place only if it can be
declared and verified. Measured, 7 of 24 declarations met it. The rule was true
of the design and false of most of the language, and nothing said so, because
feasibility and the audit are separate modules and neither is related to the
list of declarations they cover.

These tests make the registry binding. A name in it that does not exist in the
code fails here, so the file cannot rot into a wish list, and the coverage floor
only ever moves up.
"""

import re
from pathlib import Path

import pytest

from misata import registry
from misata.compat import HANDLED_TOP_LEVEL_KEYS

_FEASIBILITY = Path(registry.__file__).with_name("feasibility.py").read_text()
_COHERENCE = Path(registry.__file__).with_name("coherence.py").read_text()


class TestTheRegistryIsTrue:
    """A registry nobody checks is a second place for the docs to be wrong."""

    @pytest.mark.parametrize("decl", [d for d in registry.DECLARATIONS if d.refusal],
                             ids=lambda d: d.key)
    def test_the_named_refusal_exists(self, decl):
        assert re.search(rf"def {re.escape(decl.refusal)}\b", _FEASIBILITY), (
            f"{decl.key} claims {decl.refusal!r} refuses it early, and no such "
            f"function exists in feasibility.py"
        )

    @pytest.mark.parametrize("decl", [d for d in registry.DECLARATIONS if d.refusal],
                             ids=lambda d: d.key)
    def test_the_named_refusal_actually_runs(self, decl):
        """Existing is not running. _check_curve_bounds was seventy lines of
        feasibility for outcome_curves, the flagship declaration, defined and
        never registered, so it had never executed. The first version of this
        test only checked the function existed and waved it straight through."""
        from misata import feasibility
        registered = {fn.__name__ for fn in feasibility._CHECKS}
        assert decl.refusal in registered, (
            f"{decl.key} names {decl.refusal!r}, which is defined but not in "
            f"feasibility._CHECKS, so it never runs"
        )

    @pytest.mark.parametrize("decl", [d for d in registry.DECLARATIONS if d.audit],
                             ids=lambda d: d.key)
    def test_the_named_audit_exists(self, decl):
        assert f'kind="{decl.audit}"' in _COHERENCE, (
            f"{decl.key} claims the audit reports {decl.audit!r}, and coherence.py "
            f"never reports that kind"
        )

    def test_every_declaration_the_engine_accepts_is_listed(self):
        """A declaration can be parsed, wired and released with neither half.
        joint_distributions was, in 0.9.6.48. This is what catches the next one."""
        # Structural keys are not declarations: they say what the schema IS.
        structural = {"tables", "name", "seed", "domain", "generation_mode",
                      "relationships", "locale", "rows", "realism"}
        accepted = set(HANDLED_TOP_LEVEL_KEYS) - structural
        listed = set(registry.ACCEPTED_KEYS)
        assert not (accepted - listed), (
            f"the engine accepts declarations the registry does not list, so "
            f"nothing is holding them to the rule: {sorted(accepted - listed)}"
        )

    def test_nothing_is_listed_twice(self):
        keys = [d.key for d in registry.DECLARATIONS]
        assert len(keys) == len(set(keys))

    def test_every_alias_really_is_accepted(self):
        """An alias nobody honours is worse than no alias."""
        for decl in registry.DECLARATIONS:
            for alias in decl.aliases:
                assert alias in HANDLED_TOP_LEVEL_KEYS, (
                    f"{decl.key} claims {alias!r} is an accepted spelling, and "
                    f"from_dict_schema does not accept it"
                )


class TestCoverageOnlyGoesUp:
    """The floor. Raise it when you close a gap; never lower it."""

    FLOOR = 14

    def test_certified_coverage_holds(self):
        certified, total = registry.coverage()
        assert certified >= self.FLOOR, (
            f"{certified}/{total} declarations are certified, below the floor of "
            f"{self.FLOOR}. Still owed: "
            f"{', '.join(d.key for d in registry.uncertified())}"
        )

    def test_the_floor_is_not_stale(self):
        """When the floor is raised, this says so, so it is not left behind."""
        certified, total = registry.coverage()
        assert certified <= self.FLOOR, (
            f"{certified}/{total} are now certified, above the floor of "
            f"{self.FLOOR}. Raise FLOOR to {certified} so the gain is locked in."
        )


class TestTheLinearCoreIsCoherent:
    """The claim that these twelve reduce to one linear system is the premise
    of the joint solve. Recorded here so it is a decision, not an assumption."""

    def test_the_exact_aggregate_family_is_all_linear(self):
        for key in ("outcome_curves", "rate_curves", "group_shares",
                    "joint_distributions", "waterfalls", "stock_flows"):
            assert registry.BY_KEY[key].linear, f"{key} is the linear core's reason to exist"

    def test_structure_is_not_claimed_linear(self):
        """A closure or a state machine is combinatorial. Claiming otherwise
        would send it to a solver that cannot express it."""
        for key in ("closures", "dag_edges", "graph_motifs", "lifecycles",
                    "event_logs", "bitemporal"):
            assert not registry.BY_KEY[key].linear
