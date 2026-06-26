#!/usr/bin/env bash
# generate_seeds.sh — Regenerate the dbt seeds from the declared schema.
#
# misata.yaml declares the answer key: monthly subscription revenue climbs from
# $50k to $200k, to the cent. seeds/expected_mrr.csv holds those same targets,
# and tests/assert_mrr_curve.sql proves the dbt model reproduces them.
# Edit misata.yaml to change the story, then re-run this.

set -euo pipefail

echo "Generating dbt seeds with Misata (declared MRR curve)..."
echo ""

# --config makes generation deterministic and curve-conformant.
# users.csv and subscriptions.csv are (re)written into seeds/;
# expected_mrr.csv (the answer key) is left untouched.
misata dbt-seed --config misata.yaml --seeds-dir seeds/ --force

echo ""
echo "Seeds written. Now run:"
echo "  dbt seed && dbt run && dbt test"
echo ""
echo "dbt test runs assert_mrr_curve.sql — it fails if monthly_mrr does not"
echo "match seeds/expected_mrr.csv to the cent."
