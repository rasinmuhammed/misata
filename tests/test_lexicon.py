"""Generative lexicons: vocabulary that keeps growing, and cannot collide.

Two properties are under test, and both were measured failures before this
existed. A fixed pool has a Heaps exponent of zero, so vocabulary stops growing
and the column is exhausted the moment a reader runs COUNT(DISTINCT). And a
semantic type INFERRED from a column name collides: thirteen distinct names,
full_name and vessel_name and chemical_name among them, all resolved to one
three-word pool of plan tiers.
"""
import collections

import numpy as np
import pytest

import misata
from misata.feasibility import InfeasibleSchema, check_feasibility
from misata.lexicon import _degeminate_join, Lexicon, LexiconSpec, builtin_specs, get_spec
from misata.schema import Column, SchemaConfig, Table


def heaps(values):
    """V(m) ~ m^beta. Natural language sits near 0.45-0.60; a pool is 0."""
    seen, pts = set(), []
    step = max(1, len(values) // 40)
    for i, v in enumerate(values, 1):
        seen.add(v)
        if i % step == 0 and i > 50:
            pts.append((i, len(seen)))
    x = np.log([p[0] for p in pts])
    y = np.log([p[1] for p in pts])
    return float(np.polyfit(x, y, 1)[0])


class TestVocabularyKeepsGrowing:
    def test_heaps_exponent_is_positive(self):
        """The property a pool can never have at any size."""
        for name in ("company_name", "vessel_name", "medical_procedure"):
            v = list(Lexicon(get_spec(name), np.random.default_rng(4)).draw(40_000))
            assert heaps(v) > 0.30, f"{name} vocabulary stopped growing"

    def test_distinct_values_far_exceed_a_hand_written_pool(self):
        v = list(Lexicon(get_spec("company_name"), np.random.default_rng(4)).draw(30_000))
        assert len(set(v)) > 5_000


class TestNoCrossTypeCollision:
    def test_no_two_types_share_a_value(self):
        sets = {n: set(Lexicon(s, np.random.default_rng(9)).draw(4_000))
                for n, s in builtin_specs().items()}
        for a in sets:
            for b in sets:
                if a < b:
                    assert not (sets[a] & sets[b]), f"{a} and {b} share values"


class TestCapacityIsHonest:
    def test_effective_capacity_is_below_raw(self):
        """Raw capacity is a lie when patterns carry different weights: a
        pattern drawn most of the time with few strings saturates first."""
        spec = get_spec("person_name")
        assert spec.effective_capacity() < spec.raw_capacity()

    def test_effective_capacity_predicts_duplication(self):
        spec = LexiconSpec(
            name="tiny", slots={"a": ["x", "y"], "b": ["p", "q"]},
            patterns=[("{a}{b}", 1.0)])
        v = list(Lexicon(spec, np.random.default_rng(1)).draw(500))
        assert len(set(v)) <= spec.effective_capacity()


class TestFeasibilityRefuses:
    def _schema(self, rows, semantic):
        return SchemaConfig(
            name="s", tables=[Table(name="t", row_count=rows)],
            columns={"t": [Column(name="c", type="text", semantic=semantic)]})

    def test_row_count_beyond_the_lexicon_is_refused(self):
        with pytest.raises(InfeasibleSchema):
            check_feasibility(self._schema(50_000_000, "person_name"))

    def test_unknown_semantic_type_is_refused_not_guessed(self):
        """The old behaviour was to quietly emit plan tiers instead."""
        with pytest.raises(InfeasibleSchema):
            check_feasibility(self._schema(100, "vessel_registry_code"))

    def test_repetition_natural_to_the_type_is_allowed(self):
        """Clinical coding concentrates on common procedures. Refusing all
        repetition would reject data for looking like the real thing."""
        check_feasibility(self._schema(100_000, "medical_procedure"))


class TestDeclarationBeatsInference:
    def test_declared_semantic_survives_a_guessed_text_type(self):
        """The dict path guesses text_type='name' for anything ending in
        _name, and that guess used to wipe out the declaration with it."""
        out = misata.generate_from_schema({
            "t": {"__rows__": 3_000,
                  "vessel_name": {"type": "text", "semantic": "vessel_name"}},
            "__seed__": 7})["t"]["vessel_name"]
        vals = [str(v) for v in out]
        assert len(set(vals)) > 500, "declaration was overridden by inference"
        assert any(v.startswith(("MV ", "MS ", "MT ")) for v in vals)


class TestLocaleIsNotShadowed:
    def test_region_correct_names_still_win_over_the_lexicon(self):
        """Composition adds scale. It must never cost region-correctness."""
        from misata.realism import RealisticTextGenerator

        out = {}
        for loc in ("en_US", "ja_JP"):
            g = RealisticTextGenerator(rng=np.random.default_rng(3), locale=loc)
            out[loc] = [str(x) for x in g.generate(
                "person_name", "t", 6, semantic_type="person_name",
                semantic_declared=True)]
        assert out["en_US"] != out["ja_JP"], "locale pack was shadowed"
        assert any(ord(ch) > 0x3000 for v in out["ja_JP"] for ch in v)


class TestReproducible:
    def test_same_seed_same_values(self):
        a = list(Lexicon(get_spec("vessel_name"), np.random.default_rng(5)).draw(200))
        b = list(Lexicon(get_spec("vessel_name"), np.random.default_rng(5)).draw(200))
        assert a == b


class TestComposedSurnameTail:
    """A provider's thousand-name list puts a hundred people per surname in a
    hundred-thousand-row table. Real surname stock composes, so the tail here
    does too — inside one naming tradition, because crossing traditions turns
    composition into nonsense rather than into a rare name."""

    def test_no_pairing_geminates_across_the_join(self):
        """Hart + ton is Harton, not Hartton, and Anders + sson is Andersson
        with two s and never three. Twelve of two hundred and sixty pairings
        are wrong this way, which is why they are enumerated rather than
        sampled: a defect in five percent of a pool hides for a long time.
        A double INSIDE a morpheme is left alone — Ellwood is a surname."""
        import re

        from misata.lexicon import get_spec
        spec = get_spec("person_name")
        pairs = [(a, b)
                 for group in (("anglo_stem", "anglo_suffix"),
                               ("nordic_stem", "nordic_suffix"))
                 for a in spec.slots[group[0]] for b in spec.slots[group[1]]]
        assert len(pairs) > 250
        for a, b in pairs:
            joined = _degeminate_join(a, b)
            assert not re.search(r"(.)\1\1", joined), joined
            if a[-1].lower() == b[0].lower() and a[-1].lower() in "bcdfgklmnprstvwz":
                assert len(joined) == len(a) + len(b) - 1, joined

    def test_real_surnames_keep_their_doubles(self):
        """The same rule applied to a whole string turns Bell into Bel, which
        is the identical error pointing the other way. Every surname drawn is
        either a real one, unaltered, or one this spec's morphemes compose."""
        import numpy as np

        from misata.lexicon import Lexicon, _person_pools, get_spec
        spec = get_spec("person_name")
        _given, family = _person_pools()
        composed = {_degeminate_join(a, b)
                    for group in (("anglo_stem", "anglo_suffix"),
                                  ("nordic_stem", "nordic_suffix"))
                    for a in spec.slots[group[0]] for b in spec.slots[group[1]]}
        legal = set(family) | composed | {h.split()[-1] for h in spec.head}
        drawn = {str(v).split()[-1] for v in
                 Lexicon(spec, np.random.default_rng(11)).draw(200_000)}
        assert not (drawn - legal), sorted(drawn - legal)[:10]
        # and the doubles the pool really carries are among what came out
        doubled = {f for f in family if any(f[i] == f[i + 1] for i in range(len(f) - 1))}
        assert len(doubled & drawn) > 50

    def test_the_tail_widens_the_surname_stock(self):
        import numpy as np

        from misata.lexicon import Lexicon, _person_pools, get_spec
        _given, family = _person_pools()
        drawn = {str(v).split()[-1] for v in
                 Lexicon(get_spec("person_name"), np.random.default_rng(3)).draw(200_000)}
        assert len(drawn) > len(family) + 200

    def test_elision_is_off_unless_a_spec_asks_for_it(self):
        from misata.lexicon import builtin_specs
        for name, spec in builtin_specs().items():
            if name != "person_name":
                assert not spec.elide_boundary_doubles, name
