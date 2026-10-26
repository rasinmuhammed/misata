"""Run the documentation the way a stranger would.

The test suite drives the Python API; the docs describe a command line and a
YAML file. This pulls every runnable example out of README.md, docs/ and the
use-case recipes in examples/usecases/, runs each page top to bottom in its
own sandbox, and reports what fails.

    python tools/stranger.py                 # current interpreter, fast
    python tools/stranger.py --clean         # fresh venv from the built wheel

`--clean` is the one that matters: an editable install hides packaging bugs
such as a module that needs an extra the docs never mention. In that mode a
page's `pip install "misata[...]"` line installs those extras into the venv,
as it would for a reader.

Only misata commands and the verify.py scripts Misata writes run. A doc is
not a trusted script, and nothing here may delete a directory because a
markdown file says so.
"""

from __future__ import annotations

import argparse
import json
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
    r"postgres|postgresql|mysql|sqlite:/|--db-url|(?<![-\w])seed\b|--truncate|serve|studio|"
    r"--use-llm|--provider|groq|openai|ollama|bedrock|kaggle|wikidata|prisma|dbt|"
    r"spark|delta|--sqlalchemy|localhost|127\.0\.0\.1|<|\$\{|YOUR_|xxx",
    re.I,
)

SKIP_MARKER = "stranger: skip"
# Flags whose value is a file the command writes, not one it reads.
OUTPUT_FLAGS = {"-o", "--output", "--out", "--db"}

# The verifiers Misata writes beside a dataset or an evalpack.
VERIFIER = re.compile(r"(^|/)verify(_attestation)?\.py$")

# docs/usecases/ holds copies of the recipe pages, which run from examples/.
RECIPE_COPIES = ROOT / "docs" / "usecases"

# A YAML block whose first line is a comment naming a file, such as
# `# solve.yaml`, is that file: the commands after it on the page read it.
NAMED_FILE = re.compile(r"\A#\s*([\w.-]+\.ya?ml)\s*$", re.M)

ENVELOPE_SCHEMA = ROOT / "misata" / "_schemas" / "cli-envelope.schema.json"
EXIT_CODES = {0: "ok", 1: "failed", 2: "usage", 3: "infeasible"}

# Command groups: their subcommand is part of what makes a command distinct.
GROUPS = {"capsule", "mcp", "recipe"}


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


def envelope_problem(process: subprocess.CompletedProcess) -> str:
    """Why a ``--json`` run's stdout is not a valid envelope, or "" when it is."""
    try:
        envelope = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        return f"stdout is not one JSON document ({exc.msg})"
    try:
        import jsonschema
    except ImportError:
        schema = json.loads(ENVELOPE_SCHEMA.read_text())
        missing = sorted(set(schema["required"]) - set(envelope))
        if missing:
            return f"missing {missing}"
    else:
        try:
            jsonschema.validate(envelope, json.loads(ENVELOPE_SCHEMA.read_text()))
        except jsonschema.ValidationError as exc:
            return f"schema: {exc.message}"
    if envelope["exit_code"] != process.returncode:
        return f"exit_code {envelope['exit_code']} but the process exited {process.returncode}"
    if EXIT_CODES.get(process.returncode, "failed") != envelope["code"]:
        return f"code {envelope['code']!r} for exit {process.returncode}"
    return ""


class Runner:
    def __init__(self, python: Path, wheel: Path | None = None):
        self.python = python
        self.wheel = wheel
        self.enveloped: set = set()
        self.installed: set = set()
        self.shipped: set = set()

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
        if head.startswith("python") and len(tokens) > 1 and (
                VERIFIER.search(tokens[1]) or (cwd / tokens[1]).resolve() in self.shipped):
            return self.run_script(tokens, cwd)
        if head == "pytest" and len(tokens) > 1 and (cwd / tokens[1]).resolve() in self.shipped:
            return self.run_pytest(tokens, cwd)
        if NEEDS_WORLD.search(line):
            return "skip", "needs a database, a key, or a placeholder"
        if head != "misata":
            return "skip", "not a misata command"
        if "publish" in tokens[1:2] and "--dry-run" not in tokens:
            return "skip", "uploads to the Hugging Face Hub"
        # An example that reads a file the docs never ship is documentation, not
        # a broken command.
        for previous, tok in zip(tokens[:-1], tokens[1:]):
            if previous in OUTPUT_FLAGS:
                continue
            if tok.endswith(DATA_SUFFIXES) and not (cwd / tok).exists():
                return "skip", f"needs an input file the docs do not ship ({tok})"
        try:
            p = self.misata(tokens[1:], cwd)
            problem = self.check_envelope(tokens, cwd)
        except subprocess.TimeoutExpired:
            return "fail", "timed out after 300s"
        if problem:
            return "fail", f"--json envelope: {problem}"
        if p.returncode != 0:
            tail = (p.stderr or p.stdout).strip().splitlines()
            detail = tail[-1] if tail else f"exit {p.returncode}"
            if "already exists" in detail and "--force" in detail:
                return "skip", "an alternative spelling of a command already run"
            return "fail", detail
        return "pass", ""

    def run_script(self, tokens: list[str], cwd: Path):
        """A verify.py Misata wrote into the sandbox, or a script the recipe ships.

        Nothing else runs as Python.
        """
        script = (cwd / tokens[1]).resolve()
        if not script.is_file() or cwd.resolve() not in script.parents:
            return "skip", f"needs a verifier the page has not written yet ({tokens[1]})"
        for tok in tokens[2:]:
            if tok.endswith(DATA_SUFFIXES + (".jsonl",)) and not (cwd / tok).exists():
                return "skip", f"needs an input file the docs do not ship ({tok})"
        try:
            done = subprocess.run([str(self.python), *tokens[1:]], cwd=cwd,
                                  capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired:
            return "fail", "timed out after 300s"
        if done.returncode != 0:
            tail = (done.stdout + done.stderr).strip().splitlines()
            return "fail", tail[-1] if tail else f"exit {done.returncode}"
        return "pass", ""

    def run_pytest(self, tokens: list[str], cwd: Path):
        """A test file the recipe ships, run with the misata pytest plugin loaded."""
        try:
            done = subprocess.run([str(self.python), "-m", "pytest", "-q", "-p", "no:cacheprovider",
                                   *tokens[1:]], cwd=cwd, capture_output=True, text=True,
                                  timeout=300)
        except subprocess.TimeoutExpired:
            return "fail", "timed out after 300s"
        if done.returncode != 0:
            tail = (done.stdout + done.stderr).strip().splitlines()
            return "fail", tail[-1] if tail else f"exit {done.returncode}"
        return "pass", ""

    def check_envelope(self, tokens: list[str], cwd: Path) -> str:
        """Rerun the first documented use of each command with --json."""
        name = tuple(tokens[1:3] if len(tokens) > 2 and tokens[1] in GROUPS else tokens[1:2])
        if not name or name[0].startswith("-") or name in self.enveloped or "--json" in tokens:
            return ""
        self.enveloped.add(name)
        return envelope_problem(self.misata([*tokens[1:], "--json"], cwd))

    def check_pip(self, tokens: list[str]):
        """A documented `misata[extra]` must be an extra that exists.

        Checked against pyproject, offline. In --clean mode the extras are then
        installed into the venv, so the commands after this line run with
        exactly what the page told the reader to install.
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
        # A tool the page also installs and then runs, such as pytest.
        tools = [tok for tok in tokens if tok == "pytest"]
        if self.wheel is not None and not (wanted | set(tools)) <= self.installed:
            subprocess.run([str(self.python), "-m", "pip", "-q", "install",
                            f"{self.wheel}[{','.join(sorted(wanted))}]", *tools],
                           check=True, capture_output=True)
            self.installed |= wanted | set(tools)
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


def clean_python(workdir: Path) -> tuple[Path, Path]:
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
    return py, wheel


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clean", action="store_true",
                    help="fresh venv from the built wheel (the honest mode)")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--only", metavar="TEXT", help="run only pages whose path contains TEXT")
    args = ap.parse_args()

    docs = sorted(ROOT.glob("docs/**/*.md")) + [ROOT / "README.md"]
    docs += sorted(ROOT.glob("examples/usecases/*/README.md"))
    docs = [d for d in docs if d.exists() and RECIPE_COPIES not in d.parents
            and (args.only is None or args.only in d.relative_to(ROOT).as_posix())]
    examples = extract(docs)

    workdir = Path(tempfile.mkdtemp(prefix="stranger-"))
    try:
        python, wheel = clean_python(workdir) if args.clean else (Path(sys.executable), None)
        runner = Runner(python, wheel)

        # One sandbox per document, blocks in reading order. A reader works
        # down a page: `misata init` in one block and `misata generate` in the
        # next is a sequence, and giving each block a fresh directory made the
        # harness report "no misata.yaml" as a documentation bug.
        results = []
        sandboxes: dict = {}
        for ex in examples:
            sandbox = sandboxes.get(ex.source)
            if sandbox is None:
                sandbox = sandboxes[ex.source] = Path(tempfile.mkdtemp(dir=workdir))
                # A recipe's page reads the files beside it.
                if ex.source.parent.parent == ROOT / "examples" / "usecases":
                    shutil.copytree(ex.source.parent, sandbox, dirs_exist_ok=True,
                                    ignore=shutil.ignore_patterns("README.md", "out*"))
                    runner.shipped |= {(sandbox / p.name).resolve()
                                       for p in ex.source.parent.glob("*.py")}
            if ex.lang == "yaml":
                named = NAMED_FILE.match(ex.body)
                if named:
                    (sandbox / named.group(1)).write_text(ex.body)
                if not looks_like_a_schema(ex.body):
                    detail = f"written as {named.group(1)}" if named else "not a misata schema"
                    results.append((ex, "skip", detail, ""))
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
