"""Two promises the README makes, now enforced.

`Lorem ipsum cannot reach output` was not true: `text_type: "word"` returned a
word straight from a Lorem Ipsum pool, and a `cost_centre` column on the public
star-schema page was full of "veniam" and "consectetur".

And a date dimension is a calendar, not a sample. Generating month, quarter and
year as three independent columns produced June 2024 labelled Q4 2025 on that
same page. `Table.inline_data` existed; the dict path dropped the key silently.
"""

import re

import pytest

import misata

LOREM = re.compile(
    r"\b(lorem|ipsum|dolor|consectetur|adipiscing|eiusmod|tempor|ullamco|"
    r"aliquip|commodo|veniam|nostrud|laboris|incididunt)\b", re.I)

TEXT_TYPES = ["word", "sentence", "text", "paragraph", "description",
              "notes", "comment"]


@pytest.mark.parametrize("text_type", TEXT_TYPES)
def test_no_text_type_can_emit_lorem_ipsum(text_type):
    cols = {"id": {"type": "integer", "primary_key": True},
            "value": {"type": "string", "text_type": text_type}}
    data = misata.generate_from_schema(
        misata.from_dict_schema({"t": {"__rows__": 40, **cols}}, seed=9))["t"]
    offenders = [v for v in data["value"].astype(str) if LOREM.search(v)]
    assert not offenders, f"{text_type} emitted lorem: {offenders[:2]}"


def test_a_word_is_a_label_not_a_paragraph():
    """`word` means a short label. A column called cost_centre should not come
    back holding a sentence."""
    data = misata.generate_from_schema(misata.from_dict_schema(
        {"t": {"__rows__": 20,
               "id": {"type": "integer", "primary_key": True},
               "cost_centre": {"type": "string", "text_type": "word"}}},
        seed=5))["t"]
    assert all(len(str(v).split()) == 1 for v in data["cost_centre"])


def _calendar(months=6, year=2024):
    return [{"date_key": int(f"{year}{m:02d}"),
             "snapshot_month": f"{year}-{m:02d}",
             "quarter": f"Q{(m - 1) // 3 + 1}",
             "year": year} for m in range(1, months + 1)]


def test_inline_reference_rows_are_used_verbatim():
    rows = _calendar()
    data = misata.generate_from_schema(misata.from_dict_schema({
        "dim_date": {"__inline_data__": rows,
                     "date_key": {"type": "integer", "primary_key": True},
                     "snapshot_month": {"type": "string"},
                     "quarter": {"type": "string"},
                     "year": {"type": "integer"}}}, seed=1))["dim_date"]

    assert len(data) == len(rows), "row count must follow the data given"
    assert list(data["snapshot_month"]) == [r["snapshot_month"] for r in rows]
    assert list(data["quarter"]) == [r["quarter"] for r in rows]
    assert set(data["year"]) == {2024}


def test_a_month_always_agrees_with_its_quarter():
    """The defect this exists to stop: 2024-06 labelled Q4 of 2025."""
    data = misata.generate_from_schema(misata.from_dict_schema({
        "dim_date": {"__inline_data__": _calendar(12),
                     "date_key": {"type": "integer", "primary_key": True},
                     "snapshot_month": {"type": "string"},
                     "quarter": {"type": "string"},
                     "year": {"type": "integer"}}}, seed=3))["dim_date"]

    for _, row in data.iterrows():
        year, month = str(row["snapshot_month"]).split("-")
        assert int(year) == int(row["year"])
        assert row["quarter"] == f"Q{(int(month) - 1) // 3 + 1}"


def test_a_fact_table_still_joins_to_inline_reference_rows():
    data = misata.generate_from_schema(misata.from_dict_schema({
        "dim_date": {"__inline_data__": _calendar(),
                     "date_key": {"type": "integer", "primary_key": True},
                     "snapshot_month": {"type": "string"},
                     "quarter": {"type": "string"},
                     "year": {"type": "integer"}},
        "fact_headcount": {"__rows__": 50,
                           "id": {"type": "integer", "primary_key": True},
                           "date_key": {"type": "integer",
                                        "foreign_key": {"table": "dim_date",
                                                        "column": "date_key"}},
                           "headcount": {"type": "integer", "min": 1, "max": 90}}},
        seed=1))
    assert data["fact_headcount"]["date_key"].isin(data["dim_date"]["date_key"]).all()
