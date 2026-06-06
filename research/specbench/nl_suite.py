"""
E12 — suite-level NL conformance across 18 domains, through two parsers.

For each domain we state a monthly outcome curve in one English sentence (a January anchor
rising to a December anchor) and ask: does the natural-language path produce a relational
dataset whose realized monthly rollup hits the declared curve? We run two parsers behind the
same engine:
  - rule:  misata.parse (the rule-based StoryParser; no API key)
  - llm:   LLMSchemaGenerator(provider="groq") (Llama-3.3-70b)

Per (domain, parser) we record: curve_detected, anchor_match (did the parser read the stated
Jan/Dec anchors), AME (engine conformance to the extracted curve), FIVR, DET. The aggregate
is the suite-level claim the paper makes about the NL front-end.

Run:  set -a; source .env; set +a; PYTHONPATH=. python3 research/specbench/nl_suite.py
"""
from __future__ import annotations
import warnings; warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

import misata
from research.specbench.metrics import fk_integrity_violation_rate

# (domain, sentence, jan_anchor, dec_anchor)
STORIES = [
    ("saas",          "A SaaS company with 2000 customers: monthly recurring revenue 50000 in January rising to 200000 in December.", 50000, 200000),
    ("ecommerce",     "An ecommerce store with 3000 customers: revenue 80000 in January rising to 300000 in December.", 80000, 300000),
    ("fintech",       "A fintech app: transaction volume 100000 in January rising to 400000 in December.", 100000, 400000),
    ("healthcare",    "A healthcare clinic: monthly billing 120000 in January rising to 250000 in December.", 120000, 250000),
    ("hr",            "An HR platform: monthly payroll processed 200000 in January rising to 500000 in December.", 200000, 500000),
    ("logistics",     "A logistics company: monthly shipping revenue 90000 in January rising to 260000 in December.", 90000, 260000),
    ("marketplace",   "An online marketplace: gross merchandise value 150000 in January rising to 600000 in December.", 150000, 600000),
    ("social",        "A social app: monthly ad revenue 30000 in January rising to 180000 in December.", 30000, 180000),
    ("real_estate",   "A real estate platform: monthly commission revenue 70000 in January rising to 220000 in December.", 70000, 220000),
    ("pharma",        "A pharmacy chain: monthly sales 110000 in January rising to 340000 in December.", 110000, 340000),
    ("food_delivery", "A food delivery app: monthly order revenue 95000 in January rising to 280000 in December.", 95000, 280000),
    ("edtech",        "An edtech platform: monthly course revenue 40000 in January rising to 160000 in December.", 40000, 160000),
    ("gaming",        "A gaming studio: monthly in-app purchase revenue 60000 in January rising to 240000 in December.", 60000, 240000),
    ("crm",           "A CRM SaaS: monthly subscription revenue 55000 in January rising to 210000 in December.", 55000, 210000),
    ("crypto",        "A crypto exchange: monthly trading fee revenue 130000 in January rising to 520000 in December.", 130000, 520000),
    ("insurance",     "An insurance company: monthly premium revenue 140000 in January rising to 360000 in December.", 140000, 360000),
    ("travel",        "A travel booking site: monthly booking revenue 85000 in January rising to 310000 in December.", 85000, 310000),
    ("streaming",     "A streaming service: monthly subscription revenue 45000 in January rising to 230000 in December.", 45000, 230000),
]

ROWS = 2000
SEED = 42


def _month_series(df, time_col):
    if time_col in df.columns:
        s = df[time_col]
    else:
        dt = [c for c in df.columns if np.issubdtype(df[c].dtype, np.datetime64)]
        if not dt:
            return None
        s = df[dt[0]]
    if np.issubdtype(s.dtype, np.number):
        return s.astype(int)
    return pd.to_datetime(s, errors="coerce").dt.month


def _ame(tables, curve):
    df = tables.get(curve.table)
    if df is None or curve.column not in df.columns:
        return np.nan
    month = _month_series(df, curve.time_column)
    if month is None:
        return np.nan
    roll = df.groupby(month)[curve.column].sum()
    errs = []
    for p in curve.curve_points:
        m, tgt = int(p["month"]), float(p["target_value"])
        if tgt == 0:
            continue
        got = float(roll.get(m, 0.0))
        errs.append(abs(got - tgt) / abs(tgt))
    return max(errs) if errs else np.nan


def _fks(schema):
    return [(r.parent_table, r.parent_key, r.child_table, r.child_key)
            for r in getattr(schema, "relationships", []) or []]


def _anchors(curve):
    pts = {int(p["month"]): float(p["target_value"]) for p in curve.curve_points}
    return pts.get(1), pts.get(12)


def parse_rule(story):
    return misata.parse(story, rows=ROWS)


import os as _os
OPENAI_MODEL = _os.environ.get("OPENAI_MODEL", "gpt-5.3-chat-latest")


def parse_openai(story, model=None):
    """OpenAI GPT-5-class path. The library handles the modern parameter shape
    (max_completion_tokens, model-default temperature) for these models. Newer models return
    strict JSON, so no tolerant cleaning is needed. Model is overridable via OPENAI_MODEL."""
    from misata.llm_parser import LLMSchemaGenerator
    gen = LLMSchemaGenerator(provider="openai", model=model or OPENAI_MODEL)
    for _ in range(2):
        schema = gen.generate_from_story(story, default_rows=ROWS, temperature=1.0)
        if getattr(schema, "outcome_curves", None):
            return schema
    return schema


_LAST_STRICT_OK = True


def parse_llm(story):
    """Groq Llama-3.3 parse at temperature 0. We tolerate loose JSON (the model sometimes
    embeds `#` comments or trailing commas that Groq's strict json_object mode rejects), and
    record whether strict mode would have accepted the output, since that brittleness is part
    of the honest LLM-reliability picture."""
    import re, types
    global _LAST_STRICT_OK
    from misata.llm_parser import LLMSchemaGenerator
    gen = LLMSchemaGenerator(provider="groq")

    def _tolerant_call(self, messages, max_tokens, temperature):
        global _LAST_STRICT_OK
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages,
            temperature=temperature, max_tokens=max_tokens)   # no json_object: get raw text
        txt = resp.choices[0].message.content
        cleaned = re.sub(r'//.*', '', re.sub(r'#.*', '', txt))
        cleaned = re.sub(r',(\s*[}\]])', r'\1', cleaned)
        _LAST_STRICT_OK = (cleaned == txt)                     # would strict json mode pass?
        return cleaned

    gen._call_openai_compatible = types.MethodType(_tolerant_call, gen)
    for _ in range(2):
        schema = gen.generate_from_story(story, default_rows=ROWS, temperature=0.0)
        if getattr(schema, "outcome_curves", None):
            return schema
    return schema


def evaluate(parser_name, parse_fn):
    rows = []
    for domain, story, jan, dec in STORIES:
        rec = {"parser": parser_name, "domain": domain, "curve_detected": False,
               "anchor_match": False, "AME": np.nan, "FIVR": np.nan, "DET": np.nan}
        try:
            schema = parse_fn(story)
            schema.seed = SEED
            curves = getattr(schema, "outcome_curves", None) or []
            if curves:
                c = curves[0]
                rec["curve_detected"] = True
                a1, a12 = _anchors(c)
                rec["anchor_match"] = bool(a1 == jan and a12 == dec)
                t1 = misata.generate_from_schema(schema)
                t2 = misata.generate_from_schema(schema)
                rec["AME"] = _ame(t1, c)
                fks = _fks(schema)
                rec["FIVR"] = fk_integrity_violation_rate(t1, fks).value if fks else 0.0
                # determinism: same seed -> identical metric column
                d = t1.get(c.table); e = t2.get(c.table)
                rec["DET"] = 1.0 if (d is not None and e is not None
                                     and d[c.column].reset_index(drop=True).equals(
                                         e[c.column].reset_index(drop=True))) else 0.0
        except Exception as ex:
            rec["error"] = str(ex)[:120]
        rows.append(rec)
        print(f"  {parser_name:<5} {domain:<14} detected={rec['curve_detected']} "
              f"anchors={rec['anchor_match']} AME={rec['AME']} FIVR={rec['FIVR']} DET={rec['DET']}")
    return rows


def summarize(df, parser):
    d = df[df.parser == parser]
    n = len(d)
    det = d.curve_detected.sum()
    ran = d[d.curve_detected]
    ame_ok = (ran.AME < 1e-6).sum() if len(ran) else 0
    print(f"\n[{parser}] domains={n}  curve_detected={det}/{n}  "
          f"anchor_match={d.anchor_match.sum()}/{n}  "
          f"AME<1e-6={ame_ok}/{det}  mean_AME={ran.AME.mean():.2e}  "
          f"FIVR=0:{int((ran.FIVR==0).sum())}/{det}  DET=1:{int((ran.DET==1).sum())}/{det}")


def evaluate_slice(parser_name, parse_fn, start, count):
    """Evaluate STORIES[start:start+count], writing each domain to a parser-specific CSV
    immediately and skipping domains already recorded, so a run that is interrupted by a
    time cap resumes cleanly on the next invocation."""
    import os
    parts = f"research/specbench/results_nl_suite_{parser_name}_run.csv"
    done = set()
    if os.path.exists(parts):
        try:
            done = set(pd.read_csv(parts, engine="python", on_bad_lines="skip")["domain"].astype(str))
        except Exception:
            done = set()
    cols = ["parser", "domain", "curve_detected", "anchor_match", "AME", "FIVR", "DET",
            "strict_json_ok", "error"]
    sub = [s for s in STORIES[start:start + count] if s[0] not in done]
    rows = []
    for domain, story, jan, dec in sub:
        rec = {"parser": parser_name, "domain": domain, "curve_detected": False,
               "anchor_match": False, "AME": np.nan, "FIVR": np.nan, "DET": np.nan,
               "strict_json_ok": np.nan}
        try:
            schema = parse_fn(story)
            if parser_name == "llm":
                rec["strict_json_ok"] = 1.0 if _LAST_STRICT_OK else 0.0
            schema.seed = SEED
            curves = getattr(schema, "outcome_curves", None) or []
            if curves:
                c = curves[0]
                rec["curve_detected"] = True
                a1, a12 = _anchors(c)
                rec["anchor_match"] = bool(a1 == jan and a12 == dec)
                t1 = misata.generate_from_schema(schema)
                t2 = misata.generate_from_schema(schema)
                rec["AME"] = _ame(t1, c)
                fks = _fks(schema)
                rec["FIVR"] = fk_integrity_violation_rate(t1, fks).value if fks else 0.0
                d = t1.get(c.table); e = t2.get(c.table)
                rec["DET"] = 1.0 if (d is not None and e is not None
                                     and d[c.column].reset_index(drop=True).equals(
                                         e[c.column].reset_index(drop=True))) else 0.0
        except Exception as ex:
            rec["error"] = " ".join(str(ex).split())[:120]   # one line, no commas/newlines
        rows.append(rec)
        print(f"  {parser_name:<6} {domain:<14} detected={rec['curve_detected']} "
              f"anchors={rec['anchor_match']} AME={rec['AME']} FIVR={rec['FIVR']} "
              f"DET={rec['DET']} strict={rec['strict_json_ok']}")
        # write this domain immediately so progress survives a time cap
        pd.DataFrame([rec]).reindex(columns=cols).to_csv(
            parts, mode="a", header=not os.path.exists(parts), index=False)
    return rows


if __name__ == "__main__":
    import sys
    which = sys.argv[1] if len(sys.argv) > 1 else "both"
    if which in ("llm", "openai") and len(sys.argv) >= 4:
        start, count = int(sys.argv[2]), int(sys.argv[3])
        fn = parse_llm if which == "llm" else parse_openai
        evaluate_slice(which, fn, start, count)
        sys.exit(0)
    allrows = []
    if which in ("rule", "both"):
        print("=== rule-based parser ===")
        allrows += evaluate("rule", parse_rule)
    if which in ("llm", "both"):
        print("=== groq llm parser ===")
        allrows += evaluate("llm", parse_llm)
    df = pd.DataFrame(allrows)
    out = "research/specbench/results_nl_suite.csv"
    df.to_csv(out, index=False)
    for p in df.parser.unique():
        summarize(df, p)
    print(f"\nwrote {out}")
