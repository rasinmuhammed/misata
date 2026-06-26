#!/usr/bin/env python3
"""Provider bake-off — compare schema quality across LLM providers.

Runs the same representative stories through each available provider (the
keyless rule parser, Groq, and AWS Bedrock/Claude) and prints the schemas
side by side with timing, so you can pick a default with evidence instead of
vibes.

Setup (only the providers you've configured will run; others are skipped):

    # Groq
    export GROQ_API_KEY=...

    # Bedrock (Claude). Enable model access in the Bedrock console first.
    export AWS_REGION=us-east-1
    export AWS_ACCESS_KEY_ID=...
    export AWS_SECRET_ACCESS_KEY=...
    export BEDROCK_MODEL_ID=anthropic.claude-sonnet-4-5-20250929-v1:0

Run:

    pip install 'misata[bedrock,llm]'
    python examples/provider_bakeoff.py
    python examples/provider_bakeoff.py --stories 3      # first 3 only
    python examples/provider_bakeoff.py --providers rules,bedrock
"""
from __future__ import annotations

import argparse
import os
import time
import traceback

import misata


# 8 representative stories spanning domains and data shapes.
STORIES = [
    "A SaaS company with 1,000 users and monthly subscriptions; MRR rises from $50k in January to $200k in December.",
    "An ecommerce store with customers, products, orders, and order line items; 20% of customers are repeat buyers.",
    "A fintech app with users, wallets, and transactions; flag about 2% of transactions as fraudulent.",
    "A hospital with patients, doctors, appointments, and lab results.",
    "A factory with 50 machines emitting temperature and vibration sensor readings every hour, plus maintenance work orders.",
    "A veterinary clinic with pet owners, their animals (species and breed), vaccinations, and vet appointments.",
    "A ride-hailing marketplace with riders, drivers, trips, and payments; surge pricing on 15% of trips.",
    "An online learning platform with students, instructors, courses, enrollments, and quiz attempts.",
]


def _schema_summary(schema) -> list[tuple[str, int, list[str]]]:
    """(table_name, row_count, column_names) for each table."""
    out = []
    for t in schema.tables:
        cols = [c.name for c in schema.get_columns(t.name)]
        out.append((t.name, t.row_count, cols))
    return out


def _build(provider: str, story: str):
    """Return (schema, elapsed_seconds). Raises on failure."""
    t0 = time.time()
    if provider == "rules":
        schema = misata.parse(story)
    else:
        from misata.llm_parser import LLMSchemaGenerator

        gen = LLMSchemaGenerator(provider=provider)
        schema = gen.generate_from_story(story)
    return schema, time.time() - t0


def _provider_available(provider: str) -> tuple[bool, str]:
    if provider == "rules":
        return True, ""
    if provider == "groq":
        return (bool(os.environ.get("GROQ_API_KEY")), "set GROQ_API_KEY")
    if provider == "bedrock":
        ok = bool(
            os.environ.get("AWS_BEARER_TOKEN_BEDROCK")  # the simple Bedrock API key
            or os.environ.get("AWS_ACCESS_KEY_ID")
            or os.environ.get("AWS_PROFILE")
        )
        return ok, "set AWS_BEARER_TOKEN_BEDROCK (Bedrock API key) or AWS creds, + enable model access"
    return True, ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--providers", default="rules,groq,bedrock",
                    help="comma list: rules,groq,bedrock")
    ap.add_argument("--stories", type=int, default=len(STORIES),
                    help="how many of the built-in stories to run")
    args = ap.parse_args()

    providers = [p.strip() for p in args.providers.split(",") if p.strip()]
    stories = STORIES[: args.stories]

    # Skip providers that aren't configured.
    active = []
    for p in providers:
        ok, hint = _provider_available(p)
        if ok:
            active.append(p)
        else:
            print(f"⏭  skipping '{p}' — not configured ({hint})")
    if not active:
        print("No providers available.")
        return

    bedrock_model = os.environ.get("BEDROCK_MODEL_ID", "(default)")
    print(f"\nProviders: {', '.join(active)}")
    if "bedrock" in active:
        print(f"Bedrock model: {bedrock_model}")
    print("=" * 78)

    timings: dict[str, float] = {p: 0.0 for p in active}
    failures: dict[str, int] = {p: 0 for p in active}

    for i, story in enumerate(stories, 1):
        print(f"\n[{i}/{len(stories)}] {story}")
        print("-" * 78)
        for p in active:
            try:
                schema, dt = _build(p, story)
                timings[p] += dt
                tables = _schema_summary(schema)
                ncols = sum(len(c) for _, _, c in tables)
                print(f"  {p:8} {dt:6.2f}s  {len(tables)} tables, {ncols} cols")
                for name, rows, cols in tables:
                    shown = ", ".join(cols[:8]) + ("…" if len(cols) > 8 else "")
                    print(f"      • {name} ({rows:,}) [{shown}]")
            except Exception as exc:  # noqa: BLE001
                failures[p] += 1
                print(f"  {p:8}  ERROR: {exc}")
                if os.environ.get("BAKEOFF_DEBUG"):
                    traceback.print_exc()

    print("\n" + "=" * 78)
    print("SUMMARY")
    for p in active:
        avg = timings[p] / max(len(stories), 1)
        print(f"  {p:8} total {timings[p]:6.2f}s  avg {avg:5.2f}s/story  failures {failures[p]}")
    print("\nEyeball the tables/columns above: which engine produced the most\n"
          "recognisable, domain-correct schema for your stories? Pick that as the\n"
          "default (MISATA_PROVIDER) and keep the others as fallbacks.")


if __name__ == "__main__":
    main()
