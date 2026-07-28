"""The Warren as a release gate, on the same contract as the Gauntlet.

A conformance suite that only runs when someone remembers to run it is
documentation, not a gate. This wires the Warren into pytest with the identical
`KNOWN_RED` contract: an unexpected failure fails the build, and so does a
known-red that starts passing without being promoted out of the list.

Skipped when duckdb is unavailable, since the verifier is the whole point and a
suite scored by the generator would prove nothing.
"""

import warnings

import pytest

duckdb = pytest.importorskip("duckdb")

from benchmarks.warren import KNOWN_RED, build_assertions, build_schema  # noqa: E402

import misata  # noqa: E402


@pytest.fixture(scope="module")
def results():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(build_schema())
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    out = []
    for cat, name, sql in build_assertions():
        try:
            violations = int(con.execute(sql).fetchone()[0] or 0)
            error = None
        except Exception as e:                     # a broken assertion is a fail
            violations, error = -1, str(e)[:200]
        out.append({"category": cat, "name": name, "violations": violations,
                    "error": error})
    return out


def test_no_unexpected_failures(results):
    unexpected = [r for r in results
                  if r["violations"] != 0 and r["name"] not in KNOWN_RED]
    detail = "\n".join(
        f"  [{r['category']}] {r['name']}: "
        + (f"{r['violations']:,} violating rows" if r["violations"] >= 0
           else f"ERROR {r['error']}")
        for r in unexpected)
    assert not unexpected, (
        f"{len(unexpected)} Warren assertion(s) regressed:\n{detail}")


def test_known_reds_are_still_red(results):
    """A known-red that starts passing must be promoted, not left in the list.

    Without this the roadmap silently rots: the list keeps claiming the engine
    cannot do something it now can, and the suite's score understates it.
    """
    promotable = [r["name"] for r in results
                  if r["violations"] == 0 and r["name"] in KNOWN_RED]
    assert not promotable, (
        f"these known-reds now pass and must be removed from "
        f"benchmarks/warren.py KNOWN_RED: {promotable}")


def test_the_suite_is_substantial(results):
    """Guards against the suite quietly shrinking to fit the engine."""
    assert len(results) >= 100
    assert len({r["category"] for r in results}) >= 9


def test_tenant_isolation_is_covered(results):
    """The category that exists because of a real production bug.

    `fivetran/dbt_stripe` shipped a window function with no `partition by` for
    long enough to reach production because its fixture had one account. If this
    category ever empties out, the suite has lost the point.
    """
    tenant = [r for r in results if r["category"] == "T"]
    assert len(tenant) >= 10
    assert all(r["violations"] == 0 for r in tenant)
