"""An explicitly declared text_type must beat column-name inference.

`text_type: name` written by a user and the "name" the simulator passes as its
own fallback arrived at the generator as the same value, so inference could not
tell them apart and won. A column called `full_name` declared as a person came
back "Premium", "Starter", "Scale".

`subtype` is the spelling the benchmarks and several examples use. It is absent
from the published JSON schema and was reaching nothing at all, so those columns
were quietly filled with business-note sentences.
"""

import re

import pytest

import misata

_LABELS = {"Premium", "Starter", "Scale", "Basic", "Lite", "Pro", "Ultimate",
           "Core", "Team", "Growth", "Essential", "Standard", "Plus"}


def _rows(key, names, n=6):
    cols = {"id": {"type": "int", "unique": True, "min": 1, "max": 10_000}}
    for nm in names:
        cols[nm] = {"type": "text", key: "name"}
    return misata.generate_from_schema(
        {"name": "t", "seed": 5, "tables": {"t": {"rows": n, "columns": cols}}})["t"]


@pytest.mark.parametrize("key", ["text_type", "subtype"])
@pytest.mark.parametrize("column", ["full_name", "display_name",
                                    "customer_name", "user_name"])
def test_a_declared_person_name_is_a_person_name(key, column):
    values = _rows(key, [column])[column]

    assert not (set(values) & _LABELS), (
        f"{column} declared {key}=name returned plan labels: {list(values)[:3]}")
    assert all(re.match(r"^\S+ \S+", str(v)) for v in values), (
        f"{column} declared {key}=name did not return two-part names: "
        f"{list(values)[:3]}")


def test_subtype_is_not_silently_dropped():
    """It used to fall through to free text, producing sentences."""
    values = _rows("subtype", ["full_name"])["full_name"]
    assert not any(len(str(v).split()) > 4 for v in values), \
        f"subtype was ignored and the column got prose: {list(values)[:2]}"


def test_inference_still_fires_when_nothing_was_declared():
    """The fix must not disable name inference for undeclared columns."""
    d = misata.generate_from_schema({"name": "t", "seed": 5, "tables": {"customers": {
        "rows": 6, "columns": {
            "id": {"type": "int", "unique": True, "min": 1, "max": 999},
            "email": {"type": "text"},
            "city": {"type": "text"}}}}})["customers"]
    assert all("@" in str(v) for v in d["email"]), "email inference regressed"
    assert all(str(v).strip() for v in d["city"]), "city inference regressed"
