"""Build one take-home per candidate: the same questions, their own numbers.

Each candidate's revenue targets are the course's scaled by a factor between
0.8 and 1.25, their order count moves by up to a tenth, and their seed
differs, all derived from their name so the build is reproducible. Every
answer, money or count, is therefore the candidate's own. For each candidate
this writes:

    packs/<name>/      the instructor's evalpack: answers, gold SQL, verify.py
    handouts/<name>/   what the candidate receives: the tables and the questions

Usage: python takehomes.py ada grace linus
"""

import hashlib
import json
import shutil
import sys
import warnings
from pathlib import Path

from misata.evalpack import build_evalpack
from misata.yaml_schema import load_schema_file


def variant(name: str):
    digest = int(hashlib.sha256(name.encode()).hexdigest()[:12], 16)
    factor = 0.8 + (digest % 4501) / 10_000
    schema = load_schema_file("course.yaml")
    schema.seed = 1_000 + digest % 900_000
    orders = schema.get_table("orders")
    orders.row_count = int(orders.row_count * (0.9 + (digest % 2001) / 10_000))
    for point in schema.outcome_curves[0].curve_points:
        point["target_value"] = round(point["target_value"] * factor, 2)
    return schema


def handout(pack: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    first = sorted((pack / "rotations").iterdir())[0]
    shutil.copytree(first / "tables", target / "tables")
    with open(pack / "questions.jsonl", encoding="utf-8") as fh:
        questions = [json.loads(line) for line in fh]
    lines = [f"{q['id']}. {q['question']}" for q in questions]
    (target / "questions.md").write_text("\n\n".join(lines) + "\n", encoding="utf-8")


def main(names):
    print(f"{'candidate':<10} {'seed':>7} {'questions':>9}  q001 answer")
    for name in names:
        schema = variant(name)
        pack = Path("packs") / name
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = build_evalpack(schema, pack, rotations=2)
        if not result.all_verified:
            sys.exit(f"{name}: the answer key did not verify; see {pack}/manifest.json")
        handout(pack, Path("handouts") / name)
        first = result.questions[0]
        print(f"{name:<10} {schema.seed:>7} {len(result.questions):>9}  {first.expected_answer}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["ada", "grace", "linus"])
