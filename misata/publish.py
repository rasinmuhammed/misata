"""Publish a verified dataset to the Hugging Face Hub.

A published dataset carries its spec, its attestation and the standalone
verifier, so anyone who downloads it can re-check every declared invariant
with DuckDB and nothing else. Nothing is uploaded until that same check has
passed here: every file's SHA-256 must match the attestation and every
invariant must hold on the files as they are now.

Two directory shapes publish:

* an attested dataset (``misata attest`` or ``misata generate --attest``),
  one Hub config per table;
* an evalpack (``misata evalpack``), one config per table and, for a rotated
  pack, one split per rotation, so the viewer shows each database.

The Hub token comes from ``HF_TOKEN`` or the cached ``hf auth login``;
it is never an argument and never written anywhere by Misata.

Example::

    release = prepare_hub_release("out", "acme/shop-orders", schema_path="misata.yaml")
    release.write_card()            # DATASET_CARD.md, to read before uploading
    url = publish_to_hub(release)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any, Dict, List, Literal, Optional, Sequence, Tuple, Union

import yaml

from misata import attestation_verify, evalpack_verify
from misata.exceptions import MisataError
from misata.sqlutil import quote_ident

__all__ = [
    "CARD_FILE",
    "FITTED_MARKER",
    "HubFile",
    "HubRelease",
    "PublishRefused",
    "prepare_hub_release",
    "publish_to_hub",
    "write_fitted_marker",
]

PathLike = Union[str, Path]

#: Written by ``misata mimic`` beside its output. A directory holding it was
#: fitted to real rows, and publishes only with ``allow_fitted``.
FITTED_MARKER = "fitted.json"

#: Where a dry run writes the card; the Hub repository receives it as README.md.
CARD_FILE = "DATASET_CARD.md"

TAGS = ("misata", "synthetic", "verified-synthetic")
_EVALPACK_TAGS = ("text-to-sql", "evaluation", "tabular")
_BADGE = ("[![verified by Misata](https://img.shields.io/badge/verified%20by-misata-2f6feb)]"
          f"({attestation_verify.PREDICATE_TYPE})")
_REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,95}/[A-Za-z0-9][A-Za-z0-9._-]{0,95}$")
_VIEWABLE = {".parquet", ".csv", ".jsonl"}
_INVARIANTS_SHOWN = 40
_EXPORTS = ("datacontract.odcs.yaml", "openlineage.json")


class PublishRefused(MisataError):
    """The directory cannot be published as it stands.

    ``verification_failed`` is True when the data does not hold what its
    attestation says; False when something is missing or must be confirmed.
    """

    def __init__(self, message: str, *, verification_failed: bool = False):
        super().__init__(message)
        self.verification_failed = verification_failed


@dataclass(frozen=True)
class HubFile:
    """One file of the release: its bytes come from ``local`` or ``content``."""

    path_in_repo: str
    local: Optional[Path] = None
    content: Optional[bytes] = None

    def source(self) -> Union[str, bytes]:
        if self.content is not None:
            return self.content
        assert self.local is not None
        return str(self.local)


@dataclass
class HubRelease:
    """Everything one publish uploads, checked and ready to send."""

    repo_id: str
    directory: Path
    kind: Literal["dataset", "evalpack"]
    card: str
    files: List[HubFile]
    rows: Dict[str, int]
    invariants: Tuple[int, int] = (0, 0)
    fitted: bool = False
    notes: List[str] = field(default_factory=list)

    def write_card(self, path: Optional[PathLike] = None) -> Path:
        """Write the dataset card locally; defaults to ``DATASET_CARD.md`` in the directory."""
        target = Path(path) if path is not None else self.directory / CARD_FILE
        target.write_text(self.card, encoding="utf-8")
        return target

    def to_dict(self) -> Dict[str, Any]:
        held, total = self.invariants
        return {
            "repo_id": self.repo_id,
            "kind": self.kind,
            "rows": self.rows,
            "invariants": {"held": held, "total": total},
            "fitted": self.fitted,
            "files": [f.path_in_repo for f in self.files] + ["README.md"],
        }


# --------------------------------------------------------------------------- #
# Preparing a release
# --------------------------------------------------------------------------- #

def prepare_hub_release(
    directory: PathLike,
    repo_id: str,
    *,
    license_id: str = "cc-by-4.0",
    schema_path: Optional[PathLike] = None,
    allow_fitted: bool = False,
) -> HubRelease:
    """Verify a dataset directory and assemble what publishing it uploads.

    Args:
        directory:    An attested dataset or an evalpack.
        repo_id:      The Hub dataset, ``owner/name``.
        license_id:   A Hub licence identifier for the card.
        schema_path:  The spec, when the attestation names one that is not in
                      the directory. Its digest must match the attestation.
        allow_fitted: Publish output of ``misata mimic``; the card then says
                      the data was fitted to real rows and is not anonymous.

    Raises:
        PublishRefused: the directory is not attested, a file changed since it
            was, an invariant no longer holds, the spec is missing, or the
            data was fitted and ``allow_fitted`` is False.
    """
    root = Path(directory)
    if not _REPO_ID.match(repo_id):
        raise PublishRefused(f"{repo_id!r} is not a Hub dataset id; use owner/name")
    fitted = (root / FITTED_MARKER).is_file()
    if fitted and not allow_fitted:
        raise PublishRefused(
            f"{root} was fitted to real rows by `misata mimic` ({FITTED_MARKER}). Fitted "
            "data reuses the source's category values and quantiles and is not anonymous. "
            "Publish it only if you may share the source, with --allow-fitted.")

    if (root / "questions.jsonl").is_file() and (root / "manifest.json").is_file():
        release = _evalpack_release(root, repo_id, license_id)
    else:
        release = _dataset_release(root, repo_id, license_id, schema_path, fitted)
    release.fitted = fitted
    return release


def _dataset_release(root: Path, repo_id: str, license_id: str,
                     schema_path: Optional[PathLike], fitted: bool) -> HubRelease:
    statement = _verified_statement(root)
    predicate = statement["predicate"]
    subjects = statement["subject"]
    spec_file, spec = _spec_file(root, predicate["spec"], schema_path)

    files = [HubFile(s["name"], local=attestation_verify.subject_path(root, s["name"]))
             for s in subjects]
    files.append(HubFile(attestation_verify.STATEMENT_FILE,
                         local=root / attestation_verify.STATEMENT_FILE))
    files.extend(HubFile(name, local=root / name)
                 for name in ("attestation.dsse.json", *_EXPORTS) if (root / name).is_file())
    files.append(HubFile("verify.py", content=_source_of(attestation_verify)))
    files.append(HubFile(spec_file.name, local=spec_file))
    if fitted:
        files.append(HubFile(FITTED_MARKER, local=root / FITTED_MARKER))

    rows = _row_counts(root, subjects)
    checked = predicate["invariants"]
    held = sum(1 for invariant in checked if invariant["passed"])
    configs = [{"config_name": table, "data_files": paths}
               for table, paths in _viewable_files(subjects).items()]
    name = str(spec.get("name") or root.resolve().name)
    card = _front_matter(license_id, name, sum(rows.values()), configs, evalpack=False) + \
        _dataset_body(name, spec, spec_file.name, predicate, rows, fitted, _format_of(subjects))
    return HubRelease(repo_id=repo_id, directory=root, kind="dataset", card=card,
                      files=_unique(files), rows=rows, invariants=(held, len(checked)))


def _evalpack_release(root: Path, repo_id: str, license_id: str) -> HubRelease:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    certificate = json.loads((root / "certificate.json").read_text(encoding="utf-8"))
    if not certificate.get("all_match"):
        raise PublishRefused("certificate.json records answers that do not match; rebuild "
                             "the pack", verification_failed=True)
    questions = evalpack_verify.load_questions(root)
    failures, report = evalpack_verify.check(
        root, {qid: q["gold_sql"] for qid, q in questions.items()})
    if failures:
        raise PublishRefused(
            f"{failures} gold quer{'y' if failures == 1 else 'ies'} no longer return the "
            "expected answer:\n" + "\n".join(line for line in report if line.startswith("FAIL")),
            verification_failed=True)

    files = [HubFile(name, local=root / name)
             for name in ("questions.jsonl", "certificate.json", "manifest.json")]
    files.append(HubFile("verify.py", content=_source_of(evalpack_verify)))
    splits: Dict[str, List[Dict[str, str]]] = {}
    held = total = 0
    databases = evalpack_verify.databases(root)
    for label, tables_dir in databases:
        database = tables_dir.parent
        statement = _verified_statement(database)
        prefix = database.relative_to(root).as_posix()
        prefix = "" if prefix == "." else prefix + "/"
        for subject in statement["subject"]:
            files.append(HubFile(prefix + subject["name"],
                                 local=attestation_verify.subject_path(database, subject["name"])))
        for name in (attestation_verify.STATEMENT_FILE, "attestation.dsse.json",
                     "certificate.json" if prefix else ""):
            if name and (database / name).is_file():
                files.append(HubFile(prefix + name, local=database / name))
        files.append(HubFile(prefix + "verify_attestation.py",
                             content=_source_of(attestation_verify)))
        checked = statement["predicate"]["invariants"]
        held += sum(1 for invariant in checked if invariant["passed"])
        total += len(checked)
        split = re.sub(r"\W", "_", label) if len(databases) > 1 else "train"
        for table, paths in _viewable_files(statement["subject"]).items():
            for path in paths:
                splits.setdefault(table, []).append({"split": split, "path": prefix + path})

    configs = [{"config_name": table, "data_files": entries} for table, entries in splits.items()]
    first = manifest.get("rotations", [{}])[0].get("tables") or manifest.get("tables", {})
    rows = {str(k): int(v) for k, v in first.items()}
    name = str(manifest.get("pack") or root.resolve().name)
    card = _front_matter(license_id, name, sum(rows.values()) * max(len(databases), 1),
                         configs, evalpack=True) + \
        _evalpack_body(name, manifest, questions, rows, len(databases), (held, total))
    return HubRelease(repo_id=repo_id, directory=root, kind="evalpack", card=card,
                      files=_unique(files), rows=rows, invariants=(held, total))


def _verified_statement(directory: Path) -> Dict[str, Any]:
    """The directory's Statement, after every digest and invariant re-checks."""
    if not (directory / attestation_verify.STATEMENT_FILE).is_file():
        raise PublishRefused(
            f"{directory} has no {attestation_verify.STATEMENT_FILE}. Attest it first: "
            f"misata attest {directory} --schema misata.yaml")
    try:
        statement = attestation_verify.load_statement(directory)
        ok, report = attestation_verify.verify(directory)
    except (OSError, ValueError, KeyError) as exc:
        raise PublishRefused(f"cannot read the attestation in {directory}: {exc}") from exc
    if statement["predicate"].get("result") != "PASSED" or not ok:
        failing = [line for line in report if line.startswith("FAIL")]
        raise PublishRefused(
            f"{directory} does not hold what its attestation says:\n" + "\n".join(failing),
            verification_failed=True)
    return statement


def _spec_file(root: Path, spec: Dict[str, Any],
               schema_path: Optional[PathLike]) -> Tuple[Path, Dict[str, Any]]:
    """The spec file the attestation pins, and its parsed contents."""
    want = spec["digest"]["sha256"]
    candidates = [Path(schema_path)] if schema_path is not None else [root / spec["name"]]
    for path in candidates:
        if not path.is_file():
            continue
        if attestation_verify.sha256_file(path) == want or _canonical_digest(path) == want:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
            return path, loaded if isinstance(loaded, dict) else {}
        raise PublishRefused(
            f"{path} is not the spec the attestation pins ({spec['name']}, "
            f"sha256 {want[:12]}); pass the file the data was generated from")
    raise PublishRefused(
        f"the attestation pins {spec['name']} (sha256 {want[:12]}), which is not in {root}. "
        "Pass it with --schema so the dataset carries its spec.")


def _canonical_digest(path: Path) -> Optional[str]:
    """The digest ``attest`` records for a schema passed without its file."""
    from misata.attestation import spec_reference
    from misata.yaml_schema import load_schema_file

    try:
        schema = load_schema_file(path)
    except Exception:  # noqa: BLE001 - an unreadable spec simply does not match
        return None
    return str(spec_reference(schema, None)["digest"]["sha256"])


def _row_counts(root: Path, subjects: List[Dict[str, Any]]) -> Dict[str, int]:
    con = attestation_verify.connect(root, subjects)
    try:
        tables = [t for s in subjects for t in (s.get("annotations") or {}).get("tables", [])]
        return {table: int(con.execute(f"SELECT count(*) FROM {quote_ident(table)}").fetchone()[0])
                for table in dict.fromkeys(tables)}
    finally:
        con.close()


def _viewable_files(subjects: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Per table, the paths the Hub viewer can read; partitioned tables as one glob."""
    out: Dict[str, List[str]] = {}
    for subject in subjects:
        path = PurePosixPath(subject["name"])
        tables = (subject.get("annotations") or {}).get("tables") or [path.stem]
        if path.suffix.lower() not in _VIEWABLE or len(tables) != 1:
            continue
        table = tables[0]
        if table in path.parts[:-1]:
            folder = PurePosixPath(*path.parts[:path.parts.index(table) + 1])
            entry = f"{folder}/**/*{path.suffix}"
        else:
            entry = str(path)
        if entry not in out.setdefault(table, []):
            out[table].append(entry)
    return out


def _format_of(subjects: List[Dict[str, Any]]) -> str:
    """The ``misata generate --format`` that writes files like these."""
    suffixes = {PurePosixPath(s["name"]).suffix.lower() for s in subjects}
    return next((fmt for fmt in ("parquet", "duckdb", "jsonl") if f".{fmt}" in suffixes), "csv")


def _source_of(module: Any) -> bytes:
    return Path(module.__file__).read_bytes()


def _unique(files: Sequence[HubFile]) -> List[HubFile]:
    seen: Dict[str, HubFile] = {}
    for f in files:
        seen.setdefault(f.path_in_repo, f)
    return list(seen.values())


# --------------------------------------------------------------------------- #
# The card
# --------------------------------------------------------------------------- #

_SIZE_CATEGORIES = ((1_000, "n<1K"), (10_000, "1K<n<10K"), (100_000, "10K<n<100K"),
                    (1_000_000, "100K<n<1M"), (10_000_000, "1M<n<10M"),
                    (100_000_000, "10M<n<100M"), (1_000_000_000, "100M<n<1B"))


def _size_category(rows: int) -> str:
    return next((label for bound, label in _SIZE_CATEGORIES if rows < bound), "1B<n<10B")


def _front_matter(license_id: str, name: str, rows: int, configs: List[Dict[str, Any]],
                  *, evalpack: bool) -> str:
    meta: Dict[str, Any] = {
        "license": license_id,
        "pretty_name": name,
        "tags": list(TAGS) + (list(_EVALPACK_TAGS) if evalpack else []),
        "size_categories": [_size_category(rows)],
    }
    if evalpack:
        meta["task_categories"] = ["table-question-answering"]
    if configs:
        meta["configs"] = [
            {**c, "data_files": c["data_files"][0]}
            if isinstance(c["data_files"], list) and len(c["data_files"]) == 1
            and isinstance(c["data_files"][0], str) else c
            for c in configs]
    return "---\n" + str(yaml.safe_dump(meta, sort_keys=False, allow_unicode=True)) + "---\n\n"


def _table_rows(rows: Dict[str, int]) -> str:
    lines = ["| Table | Rows |", "|---|---:|"]
    lines += [f"| `{table}` | {count:,} |" for table, count in rows.items()]
    return "\n".join(lines)


def _cell(text: Any) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _invariant_rows(invariants: List[Dict[str, Any]]) -> str:
    lines = ["| Invariant | Expected | Observed | Holds |", "|---|---:|---:|:---:|"]
    for invariant in invariants[:_INVARIANTS_SHOWN]:
        expected = invariant["expected"]
        if invariant.get("tolerance") is not None:
            expected = f"{expected} ± {invariant['tolerance']}"
        lines.append(f"| `{_cell(invariant['id'])}` | {_cell(expected)} | "
                     f"{_cell(invariant['observed'])} | {'yes' if invariant['passed'] else 'no'} |")
    hidden = len(invariants) - _INVARIANTS_SHOWN
    if hidden > 0:
        lines.append(f"\n{hidden} more in `{attestation_verify.STATEMENT_FILE}`.")
    return "\n".join(lines)


def _dataset_body(name: str, spec: Dict[str, Any], spec_name: str, predicate: Dict[str, Any],
                  rows: Dict[str, int], fitted: bool, fmt: str) -> str:
    producer = predicate.get("producer", {}).get("uri", "pkg:pypi/misata")
    version = producer.rsplit("@", 1)[-1] if "@" in producer else ""
    invariants = predicate["invariants"]
    engine = predicate.get("engine", {})
    held = sum(1 for invariant in invariants if invariant["passed"])
    origin = (
        "> **Fitted to real rows.** This dataset was produced by `misata mimic`, which "
        "reuses the source's category values and quantiles. It is not anonymous and is "
        "not a privacy guarantee."
        if fitted else
        f"No source data was used: every value comes from the declarations in `{spec_name}`."
    )
    description = f"{spec['description'].strip()}\n\n" if spec.get("description") else ""
    regenerate = "" if fitted else f"""
## Regenerate

The same spec and seed give the same rows on the same Misata version:

```bash
pip install "misata=={version}"
misata generate -c {spec_name} -o regenerated --format {fmt}
```
"""
    return f"""# {name}

{_BADGE}

{description}Generated with [Misata](https://github.com/rasinmuhammed/misata) {version} from `{spec_name}`, seed {predicate.get('seed')}.

{origin}

## Tables

{_table_rows(rows)}

## Verified invariants

{held} of {len(invariants)} hold, checked by {engine.get('name', 'duckdb')} {engine.get('version', '')} against these exact files at {predicate.get('verifiedAt', '')}. Each is a SQL query in `{attestation_verify.STATEMENT_FILE}`, an [in-toto](https://in-toto.io) Statement that also pins every file by SHA-256.

{_invariant_rows(invariants)}

## Re-verify

```bash
pip install duckdb
python verify.py
```

`verify.py` needs only the standard library and DuckDB, and shares no code with the generator. It recomputes every file's SHA-256, re-runs every invariant, and exits 0 only when all of them hold.
{regenerate}"""


def _evalpack_body(name: str, manifest: Dict[str, Any], questions: Dict[str, Dict[str, Any]],
                   rows: Dict[str, int], databases: int, invariants: Tuple[int, int]) -> str:
    rotated = databases > 1
    seeds = manifest.get("seeds") or [manifest.get("seed")]
    where = (f"{databases} databases (seeds {seeds[0]} to {seeds[-1]}), one split each"
             if rotated else "one database")
    rule = ("\nThe databases share every declared answer and differ in every row. A query "
            "is correct only when it returns the expected answer on all of them, so a query "
            "that fits particular rows (a hard-coded key, a `LIMIT` without `ORDER BY`) "
            "fails.\n" if rotated else "")
    study = manifest.get("near_miss_study") or {}
    near_miss = ""
    if rotated and study.get("queries"):
        one = study["false_positive_rate_one_database"]
        every = study["false_positive_rate_all_databases"]
        near_miss = (f"\nOf {study['queries']:,} plausible wrong queries (the gold SQL with one "
                     f"mistake), {one:.1%} return the expected answer on a single database and "
                     f"{every:.1%} on all {databases} (`manifest.json`, `near_miss_study`).\n")
    held, total = invariants
    return f"""# {name}

{_BADGE}

An evaluation database generated from its answer key. Every expected answer
was declared before the data existed, then confirmed by running the gold SQL
with DuckDB against these exact files. {len(questions)} questions over {where}.
No source data was used.
{rule}{near_miss}
## Tables

{_table_rows(rows)}

## Files

- `questions.jsonl`: one question per line with its gold SQL and expected answer
- `certificate.json`: the per-question check, per database
- `manifest.json`: the full spec, seeds, versions and dropped candidates
- `{'rotations/<seed>/' if rotated else ''}tables/`: the database as CSV, pinned by
  `attestation.intoto.json` ({held} of {total} invariants hold)

## Score a model

```bash
pip install duckdb
python verify.py                             # every gold query, every database
python verify.py --candidates answers.jsonl  # your queries: {{"id": ..., "sql": ...}} per line
```

Generated with [Misata](https://github.com/rasinmuhammed/misata) {manifest.get('misata_version', '')}.
"""


# --------------------------------------------------------------------------- #
# Uploading
# --------------------------------------------------------------------------- #

def publish_to_hub(release: HubRelease, *, private: bool = False,
                   commit_message: Optional[str] = None) -> str:
    """Create the dataset repository if needed and upload the release in one commit.

    Returns:
        The dataset's URL on the Hub.

    Raises:
        ImportError: ``huggingface_hub`` is not installed (``misata[hf]``).
        PublishRefused: the Hub rejected the upload, usually for want of a login.
    """
    try:
        from huggingface_hub import CommitOperationAdd, HfApi
        from huggingface_hub.errors import HfHubHTTPError, LocalTokenNotFoundError
    except ImportError as exc:
        raise ImportError("publishing needs huggingface_hub: pip install \"misata[hf]\"") from exc

    api = HfApi()
    operations = [CommitOperationAdd(path_in_repo=f.path_in_repo, path_or_fileobj=f.source())
                  for f in release.files]
    operations.append(CommitOperationAdd(path_in_repo="README.md",
                                         path_or_fileobj=release.card.encode("utf-8")))
    try:
        url = api.create_repo(release.repo_id, repo_type="dataset", private=private,
                              exist_ok=True)
        api.create_commit(release.repo_id, repo_type="dataset", operations=operations,
                          commit_message=commit_message or "Publish with misata")
    except LocalTokenNotFoundError as exc:
        raise PublishRefused("not logged in to the Hub: run `hf auth login` or set "
                             "HF_TOKEN") from exc
    except HfHubHTTPError as exc:
        raise PublishRefused(f"the Hub refused the upload: {str(exc).splitlines()[0]}") from exc
    return str(url)


def write_fitted_marker(directory: PathLike, source: str, rows: Dict[str, int]) -> Path:
    """Record beside ``mimic`` output that it was fitted to real rows."""
    import misata

    path = Path(directory) / FITTED_MARKER
    path.write_text(json.dumps({
        "fitted_by": "misata mimic",
        "misata_version": misata.__version__,
        "source": Path(source).name,
        "rows": rows,
        "note": "Fitted to real rows: category values and quantiles of the source are "
                "reused. Not anonymous and not a privacy guarantee.",
    }, indent=2) + "\n", encoding="utf-8")
    return path
