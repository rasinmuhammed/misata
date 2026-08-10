"""Run the documentation the way a stranger would.

Nine defects in two days, every one of them on a path the docs tell people to
take, none of them caught by the test suite. The suite drives the internal
Python API with internal conventions; the docs describe a command line and a
YAML file. They had drifted into describing two different products, and the only
people finding out were the ones who left without filing an issue.

So: pull every runnable example out of README.md and docs/, run it, and report.

Two modes.

    python tools/stranger.py                 # current interpreter, fast
    python tools/stranger.py --clean         # fresh venv from the built wheel

`--clean` is the one that matters. An editable install hides packaging bugs: the
MCP server's missing extra (0.9.6.2) was invisible from inside this repo because
the dev environment already had `mcp`.

Only commands on ALLOWED run. A doc is not a trusted script, and nothing here
should be able to delete a directory because someone pasted the wrong line into
a markdown file.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import venv
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The first word of a command must be one of these. Everything else is reported
# as skipped, never executed.
ALLOWED = {"misata", "python", "python3", "pytest"}

# Commands that are real but cannot run unattended: they want a database, a key,
# a long-running server, or they deliberately destroy data.
NEEDS_WORLD = re.compile(
    r"postgres|postgresql|mysql|sqlite:/|--db-url|\bseed\b|--truncate|serve|studio|"
    r"--use-llm|--provider|groq|openai|ollama|bedrock|kaggle|wikidata|prisma|dbt|"
    r"spark|delta|--sqlalchemy|localhost|127\.0\.0\.1|<|\$\{|YOUR_|xxx",
    re.I,
)

SKIP_MARKER = "stranger: skip"


@dataclass
class Example:
    source: Path
    line: int
    lang: str
    body: str

    @property
    def where(self) -> str:
        return f"{self.source.relative_to(ROOT)}:{self.line}"


def extract(paths) -> list[Example]:
    """Every fenced bash/yaml block, with the line it starts on."""
    fence = re.compile(r"^```(bash|sh|console|ya?ml)\s*$", re.M)
    out: list[Example] = []
    for path in paths:
        text = path.read_text(errors="ignore")
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            m = fence.match(lines[i])
            if not m:
                i += 1
                continue
            # An HTML comment on the preceding line opts a block out.
            if i and SKIP_MARKER in lines[i - 1]:
                i += 1
                continue
            start = i + 1
            body: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                body.append(lines[i])
                i += 1
            lang = "yaml" if m.group(1).startswith("y") else "bash"
            out.append(Example(path, start, lang, "\n".join(body)))
            i += 1
    return out


def commands(example: Example) -> list[list[str]]:
    """Tokenised command lines from a shell block.

    shlex does the two things a naive split cannot: keep a quoted argument in
    one piece, and drop a trailing `# comment` without eating a `#` inside
    quotes. Getting this wrong made the harness report 35 failures that were its
    own, which is worse than no harness.
    """
    out = []
    for raw in example.body.splitlines():
        line = raw.strip().lstrip("$").strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("<", ">", "|", "✓", "✔")):   # sample output, not input
            continue
        try:
            tokens = shlex.split(line, comments=True)
        except ValueError:
            continue    # unbalanced quotes: prose, not a command
        if tokens:
            out.append(tokens)
    return out


# Arguments that name an input file the doc never ships.
DATA_SUFFIXES = (".csv", ".yaml", ".yml", ".json", ".parquet", ".db", ".sqlite",
                 ".prisma", ".xlsx", ".sql")


def looks_like_a_schema(body: str) -> bool:
    return "tables:" in body and ("columns:" in body or "rows:" in body)


class Runner:
    def __init__(self, python: Path):
        self.python = python

    def misata(self, args, cwd) -> subprocess.CompletedProcess:
        return subprocess.run([str(self.python), "-m", "misata.cli", *args],
                              cwd=cwd, capture_output=True, text=True, timeout=300)

    def run_shell(self, tokens: list[str], cwd: Path):
        line = " ".join(tokens)
        head = tokens[0]
        if head in {"pip", "pip3", "uv"} or (head.startswith("python") and "pip" in tokens):
            return self.check_pip(tokens)
        if head not in ALLOWED:
            return "skip", f"not an allowed command ({head})"
        if NEEDS_WORLD.search(line):
            return "skip", "needs a database, a key, or a placeholder"
        if head != "misata":
            return "skip", "not a misata command"
        # An example that reads a file the docs never ship is documentation, not
        # a broken command.
        for tok in tokens[1:]:
            if tok.endswith(DATA_SUFFIXES) and not (cwd / tok).exists():
                return "skip", f"needs an input file the docs do not ship ({tok})"
        try:
            p = self.misata(tokens[1:], cwd)
        except subprocess.TimeoutExpired:
            return "fail", "timed out after 300s"
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip().splitlines()
            detail = tail[-1] if tail else f"exit {p.returncode}"
            if "already exists" in detail and "--force" in detail:
                return "skip", "an alternative spelling of a command already run"
            return "fail", detail
        return "pass", ""

    def check_pip(self, tokens: list[str]):
        """A documented `misata[extra]` must be an extra that exists.

        Resolved against pyproject rather than by running pip: offline,
        instant, and it answers the only question worth asking. A README that
        tells someone to install an extra which was renamed leaves them with a
        package that imports and then dies, which is how the MCP server shipped
        broken in 0.9.6.1.
        """
        import tomllib
        spec = next((tok for tok in tokens if "misata[" in tok), None)
        if spec is None:
            return "skip", "not a misata install"
        wanted = {e.strip() for e in
                  spec.split("[", 1)[1].split("]", 1)[0].split(",")}
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        real = set(data["project"].get("optional-dependencies", {}))
        missing = sorted(wanted - real)
        if missing:
            return "fail", (f"documented extra(s) {missing} do not exist; "
                            f"available: {sorted(real)}")
        return "pass", ""

    def run_yaml(self, body: str, cwd: Path):
        (cwd / "misata.yaml").write_text(body)
        try:
            lint = self.misata(["lint", "misata.yaml"], cwd)
            gen = self.misata(
                ["generate", "--config", "misata.yaml", "--output-dir", "out"], cwd)
        except subprocess.TimeoutExpired:
            return "fail", "timed out after 300s"
        if gen.returncode != 0:
            tail = (gen.stderr or gen.stdout).strip().splitlines()
            return "fail", f"generate failed: {tail[-1] if tail else ''}"
        if lint.returncode != 0:
            # The two disagreeing is its own defect class, and it shipped twice.
            tail = (lint.stdout or "").strip().splitlines()
            return "fail", f"lint rejects what generate accepts: {tail[-1] if tail else ''}"
        return "pass", ""


def clean_python(workdir: Path) -> Path:
    """A fresh venv with the built wheel, not an editable install."""
    print("building the wheel…", flush=True)
    subprocess.run([sys.executable, "-m", "build", "-q", "-o", str(workdir / "dist")],
                   cwd=ROOT, check=True, capture_output=True)
    wheel = next((workdir / "dist").glob("*.whl"))

    print(f"creating a clean venv and installing {wheel.name}…", flush=True)
    env_dir = workdir / "venv"
    venv.EnvBuilder(with_pip=True).create(env_dir)
    py = env_dir / "bin" / "python"
    subprocess.run([str(py), "-m", "pip", "-q", "install", str(wheel)],
                   check=True, capture_output=True)
    return py


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true",
                    help="fresh venv from the built wheel (the honest mode)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    docs = sorted(ROOT.glob("docs/**/*.md")) + [ROOT / "README.md"]
    docs = [d for d in docs if d.exists()]
    examples = extract(docs)

    workdir = Path(tempfile.mkdtemp(prefix="stranger-"))
    try:
        python = clean_python(workdir) if args.clean else Path(sys.executable)
        runner = Runner(python)

        # One sandbox per document, blocks in reading order. A reader works
        # down a page: `misata init` in one block and `misata generate` in the
        # next is a sequence, and giving each block a fresh directory made the
        # harness report "no misata.yaml" as a documentation bug.
        results = []
        sandboxes: dict = {}
        for ex in examples:
            sandbox = sandboxes.setdefault(
                ex.source, Path(tempfile.mkdtemp(dir=workdir)))
            if ex.lang == "yaml":
                if not looks_like_a_schema(ex.body):
                    results.append((ex, "skip", "not a misata schema", ""))
                    continue
                status, detail = runner.run_yaml(ex.body, sandbox)
                results.append((ex, status, detail, "schema"))
            else:
                for tokens in commands(ex):
                    status, detail = runner.run_shell(tokens, sandbox)
                    results.append((ex, status, detail, " ".join(tokens)))

        ran = [r for r in results if r[1] != "skip"]
        failed = [r for r in ran if r[1] == "fail"]

        print(f"\n{len(examples)} example block(s) in {len(docs)} file(s)")
        print(f"{len(ran)} runnable, {len(ran) - len(failed)} passing, "
              f"{len(failed)} failing, {len(results) - len(ran)} skipped\n")

        if failed:
            print("FAILING:")
            for ex, _, detail, what in failed:
                print(f"  {ex.where}")
                print(f"    {what}")
                print(f"    -> {detail}\n")

        if args.verbose:
            print("SKIPPED:")
            for ex, status, detail, what in results:
                if status == "skip":
                    print(f"  {ex.where}  {what or ''}  ({detail})")

        return 1 if failed else 0
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
