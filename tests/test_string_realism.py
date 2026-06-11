"""Tests for the string-realism core: joint person identities, temporal
profiles, and Zipf–Mandelbrot categorical marginals.

These mechanisms exist to kill the classic "synthetic data tells":
nanosecond appointment timestamps, "Pablo, Female", "Wei Gonzalez",
and perfectly uniform category frequencies.
"""

import numpy as np
import pandas as pd
import pytest

import misata
from misata.people import (
    CULTURE_POOLS,
    PersonSampler,
    lookup_gender,
    lookup_surname_culture,
)
from misata.realism import apply_realism_rules
from misata.schema import Column, SchemaConfig, Table
from misata.simulator import DataSimulator
from misata.temporal_profiles import (
    DATE_ONLY,
    HUMAN_ACTION,
    MACHINE_EVENT,
    SCHEDULED,
    apply_temporal_profile,
    classify_temporal,
)


# ─── Joint person sampling ───────────────────────────────────────────────────


class TestPersonSampler:
    def test_gender_always_matches_first_name(self):
        people = PersonSampler(np.random.default_rng(0)).sample(2000)
        for first, gender in zip(people["first"], people["gender"]):
            known = lookup_gender(first)
            assert known is not None
            assert known == gender.lower()

    def test_surname_culture_mostly_matches_first_name_culture(self):
        sampler = PersonSampler(np.random.default_rng(1))
        people = sampler.sample(5000)
        match = np.mean(
            [
                lookup_surname_culture(l) == c
                for l, c in zip(people["last"], people["culture"])
            ]
        )
        # intermix rate is 6%, plus a little cross-culture surname ambiguity
        assert match > 0.80

    def test_deterministic_under_seed(self):
        a = PersonSampler(np.random.default_rng(7)).sample(100)
        b = PersonSampler(np.random.default_rng(7)).sample(100)
        assert list(a["full"]) == list(b["full"])
        assert list(a["gender"]) == list(b["gender"])

    def test_culture_mix_is_respected(self):
        sampler = PersonSampler(
            np.random.default_rng(2), mix={"japanese": 1.0}
        )
        people = sampler.sample(500)
        assert set(people["culture"]) == {"japanese"}
        # ~94% of surnames stay japanese (6% intermix falls back to mix → japanese too)
        assert all(l in CULTURE_POOLS["japanese"]["last"] for l in people["last"])

    def test_pools_are_culture_and_gender_consistent(self):
        # No name may appear in both genders of the same culture
        for culture, pools in CULTURE_POOLS.items():
            overlap = set(pools["male"]) & set(pools["female"])
            assert not overlap, f"{culture}: {overlap}"


class TestGenderNameCoherenceRule:
    def _df(self):
        return pd.DataFrame(
            {
                "first_name": ["Pablo", "Mary", "Wei", "Aisha"],
                "last_name": ["Müller", "Smith", "Zhang", "Okafor"],
                "name": ["Pablo Müller", "Mary Smith", "Wei Zhang", "Aisha Okafor"],
                "gender": ["Female", "Female", "Male", "Non-binary"],
                "email": ["x@x.com", "y@y.com", "z@z.com", "w@w.com"],
            }
        )

    def test_mismatched_names_are_replaced_keeping_gender(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        # Pablo (male name) + Female → female name; gender column untouched
        assert list(fixed["gender"]) == ["Female", "Female", "Male", "Non-binary"]
        assert lookup_gender(fixed["first_name"][0]) == "female"
        # Mary/Female was already coherent → unchanged
        assert fixed["first_name"][1] == "Mary"

    def test_replacement_respects_surname_culture(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        # Pablo Müller / Female → a german female first name (surname anchor)
        assert fixed["first_name"][0] in CULTURE_POOLS["german"]["female"]

    def test_full_name_and_email_follow_the_repair(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        new_first = fixed["first_name"][0]
        assert fixed["name"][0].startswith(new_first)
        assert new_first.lower().replace("-", "") in fixed["email"][0].replace(".", "").replace("_", "")

    def test_nonbinary_names_left_alone(self):
        fixed = apply_realism_rules(self._df(), rng=np.random.default_rng(0))
        assert fixed["first_name"][3] == "Aisha"

    def test_end_to_end_generation_has_zero_mismatches(self):
        tables = misata.generate("A hospital with 300 patients and doctors", seed=7)
        df = tables["patients"]
        declared = df["gender"].astype(str).str.lower().str[0].map(
            {"m": "male", "f": "female"}
        )
        name_gender = df["first_name"].map(lambda n: lookup_gender(n) or "")
        known = (name_gender != "") & declared.notna()
        assert known.sum() > 0
        assert (name_gender[known] == declared[known]).all()


# ─── Temporal profiles ───────────────────────────────────────────────────────


class TestTemporalProfiles:
    def test_classification(self):
        assert classify_temporal("appointment_date").name == "scheduled"
        assert classify_temporal("meeting_time").name == "scheduled"
        assert classify_temporal("date_of_birth").name == "date_only"
        assert classify_temporal("expires_at").name == "date_only"
        assert classify_temporal("created_at", "request_logs").name == "machine_event"
        assert classify_temporal("clicked_at").name == "machine_event"
        assert classify_temporal("signup_date").name == "human_action"
        assert classify_temporal("order_date").name == "human_action"

    def _dates(self, n=2000, seed=0):
        rng = np.random.default_rng(seed)
        ints = rng.integers(
            pd.Timestamp("2023-01-01").value, pd.Timestamp("2024-01-01").value, size=n
        )
        return pd.to_datetime(ints), np.random.default_rng(seed)

    def test_scheduled_snaps_to_grid_in_business_hours(self):
        dates, rng = self._dates()
        out = apply_temporal_profile(dates, SCHEDULED, rng)
        assert (out.minute % 15 == 0).all()
        assert (out.second == 0).all()
        assert (out.nanosecond == 0).all()
        assert out.hour.min() >= 7 and out.hour.max() <= 19
        assert (out.dayofweek >= 5).mean() < 0.05  # weekends damped

    def test_human_action_has_seconds_but_no_subsecond_noise(self):
        dates, rng = self._dates()
        out = apply_temporal_profile(
            dates, HUMAN_ACTION, rng, domain_hour_weights=[1] * 24
        )
        assert (out.nanosecond == 0).all()
        assert (out.microsecond == 0).all()
        assert out.second.nunique() > 30  # full second resolution

    def test_machine_events_keep_subsecond_precision(self):
        dates, rng = self._dates()
        out = apply_temporal_profile(dates, MACHINE_EVENT, rng)
        assert (out.microsecond > 0).mean() > 0.9

    def test_date_only_normalises_to_midnight(self):
        dates, rng = self._dates()
        out = apply_temporal_profile(dates, DATE_ONLY, rng)
        assert (out == out.normalize()).all()

    def test_day_distribution_is_preserved(self):
        # Profiles re-shape time-of-day, not the date histogram (modulo ±1-day
        # weekend shifts), so declared date ranges and curves stay intact.
        dates, rng = self._dates()
        out = apply_temporal_profile(
            dates, HUMAN_ACTION, rng, domain_hour_weights=[1] * 24
        )
        assert (out.normalize() == dates.normalize()).all()

    def test_end_to_end_no_nanosecond_noise_anywhere(self):
        tables = misata.generate(
            "A SaaS company with 300 users and subscriptions", seed=42
        )
        for name, df in tables.items():
            for col in df.columns:
                if pd.api.types.is_datetime64_any_dtype(df[col]):
                    assert (pd.to_datetime(df[col]).dt.nanosecond == 0).all(), (
                        f"{name}.{col} leaks nanosecond noise"
                    )


# ─── Zipf–Mandelbrot categoricals ────────────────────────────────────────────


def _generate(config):
    data = {}
    for table_name, batch_df in DataSimulator(config).generate_all():
        if table_name in data:
            data[table_name] = pd.concat([data[table_name], batch_df], ignore_index=True)
        else:
            data[table_name] = batch_df
    return data


def _categorical_schema(choices, params=None, rows=4000, seed=11):
    dist = {"choices": choices}
    if params:
        dist.update(params)
    return SchemaConfig(
        name="Test",
        seed=seed,
        tables=[Table(name="t", row_count=rows)],
        columns={
            "t": [
                Column(name="id", type="int"),
                Column(name="cat", type="categorical", distribution_params=dist),
            ]
        },
    )


class TestZipfCategoricals:
    def test_unweighted_categoricals_are_zipfian_not_uniform(self):
        config = _categorical_schema(["a", "b", "c", "d", "e"])
        df = _generate(config)["t"]
        freqs = df["cat"].value_counts(normalize=True)
        assert len(freqs) == 5                      # every choice appears
        assert freqs.iloc[0] > 1.5 * freqs.iloc[-1]  # clear head, thin tail
        assert freqs.iloc[0] > 0.25                  # visibly non-uniform (uniform = 0.20)
        # rank-frequency is monotone decreasing by construction
        assert freqs.is_monotonic_decreasing

    def test_declared_probabilities_always_win(self):
        config = _categorical_schema(
            ["x", "y"], {"probabilities": [0.9, 0.1]}
        )
        df = _generate(config)["t"]
        assert df["cat"].value_counts(normalize=True)["x"] == pytest.approx(0.9, abs=0.03)

    def test_uniform_opt_out(self):
        config = _categorical_schema(["a", "b", "c", "d"], {"sampling": "uniform"})
        df = _generate(config)["t"]
        freqs = df["cat"].value_counts(normalize=True)
        assert freqs.max() < 0.30  # ≈0.25 each

    def test_head_choice_varies_across_columns(self):
        # The rank shuffle is seeded per column: different columns should not
        # all hand dominance to the first-listed choice.
        heads = set()
        for col_name in ["status", "tier", "channel", "region", "method"]:
            config = SchemaConfig(
                name="Test",
                seed=5,
                tables=[Table(name="t", row_count=2000)],
                columns={
                    "t": [
                        Column(name="id", type="int"),
                        Column(
                            name=col_name,
                            type="categorical",
                            distribution_params={"choices": ["a", "b", "c", "d"]},
                        ),
                    ]
                },
            )
            df = _generate(config)["t"]
            heads.add(df[col_name].value_counts().index[0])
        assert len(heads) > 1

    def test_reproducible_under_seed(self):
        config = _categorical_schema(["a", "b", "c"])
        df1 = _generate(config)["t"]
        df2 = _generate(_categorical_schema(["a", "b", "c"]))["t"]
        assert list(df1["cat"]) == list(df2["cat"])

    def test_legacy_zipf_keeps_listed_order(self):
        config = _categorical_schema(
            ["first", "second", "third"], {"sampling": "zipf"}
        )
        df = _generate(config)["t"]
        freqs = df["cat"].value_counts()
        assert freqs.index[0] == "first"
