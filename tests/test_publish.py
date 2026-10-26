"""Publishing to the Hugging Face Hub: nothing leaves unless it verifies."""

from __future__ import annotations

import json
import os
import shutil
import warnings
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

import misata
from misata.attestation import attest
from misata.cli import main
from misata.publish import (CARD_FILE, FITTED_MARKER, PublishRefused, _viewable_files,
                            prepare_hub_release, publish_to_hub, write_fitted_marker)
from misata.yaml_schema import load_yaml_schema, save_yaml_schema

pytest.importorskip("duckdb")

SPEC = {
    "name": "shop",
    "description": "Orders against a declared monthly revenue curve.",
    "seed": 7,
    "tables": {
        "customers": {"rows": 120, "columns": {
            "customer_id": {"type": "int", "unique": True, "min": 1, "max": 120}}},
        "orders": {"rows": 900, "columns": {
            "order_id": {"type": "int", "unique": True, "min": 1, "max": 100000},
            "customer_id": {"type": "foreign_key"},
            "amount": {"type": "float", "min": 5, "max": 400},
            "ordered_at": {"type": "date", "start": "2025-01-01", "end": "2025-03-31"}}},
    },
    "relationships": ["customers.customer_id -> orders.customer_id"],
    "outcome_curves": [{
        "table": "orders", "column": "amount", "time_column": "ordered_at",
        "value_mode": "absolute", "start_date": "2025-01-01",
        "curve_points": [{"month": 1, "target_value": 30000},
                         {"month": 2, "target_value": 34000},
                         {"month": 3, "target_value": 41000}]}],
}


def _dataset(directory: Path, *, spec_inside: bool = True) -> Path:
    directory.mkdir(parents=True)
    spec_path = (directory if spec_inside else directory.parent) / "misata.yaml"
    spec_path.write_text(yaml.safe_dump(SPEC, sort_keys=False), encoding="utf-8")
    schema = load_yaml_schema(spec_path)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        tables = misata.generate_from_schema(schema)
    for name, df in tables.items():
        df.to_csv(directory / f"{name}.csv", index=False)
    assert attest(directory, schema, spec_path=spec_path).passed
    return directory


@pytest.fixture()
def dataset(tmp_path):
    return _dataset(tmp_path / "out")


class TestARelease:
    def test_carries_tables_spec_proof_and_verifier(self, dataset):
        release = prepare_hub_release(dataset, "acme/shop")
        paths = {f.path_in_repo for f in release.files}
        assert {"customers.csv", "orders.csv", "misata.yaml", "attestation.intoto.json",
                "attestation.dsse.json", "verify.py"} <= paths
        assert release.rows == {"customers": 120, "orders": 900}
        held, total = release.invariants
        assert held == total > 0
        assert "README.md" in release.to_dict()["files"]

    def test_the_card_is_a_valid_hub_card(self, dataset):
        hub = pytest.importorskip("huggingface_hub")
        card = hub.DatasetCard(prepare_hub_release(dataset, "acme/shop").card)
        data = card.data.to_dict()
        assert data["license"] == "cc-by-4.0"
        assert {"misata", "synthetic", "verified-synthetic"} <= set(data["tags"])
        assert data["size_categories"] == ["1K<n<10K"]
        assert {c["config_name"]: c["data_files"] for c in data["configs"]} == {
            "customers": "customers.csv", "orders": "orders.csv"}

    def test_the_card_states_what_holds_and_how_to_check(self, dataset):
        card = prepare_hub_release(dataset, "acme/shop").card
        assert "Orders against a declared monthly revenue curve." in card
        assert "No source data was used" in card
        assert "python verify.py" in card
        assert "misata generate -c misata.yaml -o regenerated --format csv" in card
        assert "| 30000.00 | 30000.00 | yes |" in card

    def test_the_licence_is_the_callers(self, dataset):
        card = prepare_hub_release(dataset, "acme/shop", license_id="mit").card
        assert card.startswith("---\nlicense: mit\n")

    def test_partitioned_tables_are_one_glob(self):
        subjects = [{"name": f"orders/region={r}/part-0.parquet",
                     "annotations": {"tables": ["orders"]}} for r in ("EU", "US")]
        subjects.append({"name": "data.duckdb", "annotations": {"tables": ["a", "b"]}})
        assert _viewable_files(subjects) == {"orders": ["orders/**/*.parquet"]}


class TestRefusals:
    def test_an_unattested_directory(self, tmp_path):
        (tmp_path / "orders.csv").write_text("id\n1\n", encoding="utf-8")
        with pytest.raises(PublishRefused, match="Attest it first") as caught:
            prepare_hub_release(tmp_path, "acme/shop")
        assert not caught.value.verification_failed

    def test_a_file_changed_after_attesting(self, dataset):
        with open(dataset / "orders.csv", "a", encoding="utf-8") as fh:
            fh.write("\n")
        with pytest.raises(PublishRefused, match="orders.csv") as caught:
            prepare_hub_release(dataset, "acme/shop")
        assert caught.value.verification_failed

    def test_a_spec_left_outside_needs_naming(self, tmp_path):
        directory = _dataset(tmp_path / "out", spec_inside=False)
        with pytest.raises(PublishRefused, match="--schema"):
            prepare_hub_release(directory, "acme/shop")
        release = prepare_hub_release(directory, "acme/shop",
                                      schema_path=tmp_path / "misata.yaml")
        assert "misata.yaml" in {f.path_in_repo for f in release.files}

    def test_a_different_spec_is_not_accepted(self, tmp_path):
        directory = _dataset(tmp_path / "out", spec_inside=False)
        other = tmp_path / "other.yaml"
        other.write_text(yaml.safe_dump({**SPEC, "seed": 8}), encoding="utf-8")
        with pytest.raises(PublishRefused, match="not the spec"):
            prepare_hub_release(directory, "acme/shop", schema_path=other)

    def test_a_spec_attested_without_its_file_matches_by_content(self, tmp_path):
        directory = tmp_path / "out"
        directory.mkdir()
        spec_path = tmp_path / "misata.yaml"
        spec_path.write_text(yaml.safe_dump(SPEC, sort_keys=False), encoding="utf-8")
        schema = load_yaml_schema(spec_path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for name, df in misata.generate_from_schema(schema).items():
                df.to_csv(directory / f"{name}.csv", index=False)
        attest(directory, schema)
        release = prepare_hub_release(directory, "acme/shop", schema_path=spec_path)
        assert release.invariants[0] == release.invariants[1]

    @pytest.mark.parametrize("repo_id", ["shop", "acme/", "/shop", "acme/shop/x", "a b/c"])
    def test_a_malformed_repo_id(self, dataset, repo_id):
        with pytest.raises(PublishRefused, match="owner/name"):
            prepare_hub_release(dataset, repo_id)

    def test_fitted_data_needs_consent_and_says_so(self, dataset):
        write_fitted_marker(dataset, "/private/customers.csv", {"customers": 120})
        with pytest.raises(PublishRefused, match="--allow-fitted"):
            prepare_hub_release(dataset, "acme/shop")
        release = prepare_hub_release(dataset, "acme/shop", allow_fitted=True)
        assert release.fitted
        assert "not anonymous" in release.card
        assert "No source data was used" not in release.card
        assert FITTED_MARKER in {f.path_in_repo for f in release.files}
        marker = json.loads((dataset / FITTED_MARKER).read_text(encoding="utf-8"))
        assert marker["source"] == "customers.csv"


class TestRotatedEvalpack:
    @pytest.fixture(scope="class")
    def pack(self, tmp_path_factory):
        from misata.evalpack import build_evalpack

        spec = tmp_path_factory.mktemp("spec") / "misata.yaml"
        spec.write_text(yaml.safe_dump(SPEC, sort_keys=False), encoding="utf-8")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = build_evalpack(load_yaml_schema(spec), tmp_path_factory.mktemp("pack"),
                                    rotations=2)
        return result.output_dir

    def test_one_config_per_table_and_one_split_per_rotation(self, pack):
        hub = pytest.importorskip("huggingface_hub")
        release = prepare_hub_release(pack, "acme/shop-pack")
        assert release.kind == "evalpack"
        configs = {c["config_name"]: c["data_files"]
                   for c in hub.DatasetCard(release.card).data.to_dict()["configs"]}
        assert configs["orders"] == [
            {"split": "seed_7", "path": "rotations/seed-7/tables/orders.csv"},
            {"split": "seed_8", "path": "rotations/seed-8/tables/orders.csv"}]

    def test_carries_questions_and_both_verifiers(self, pack):
        paths = {f.path_in_repo for f in prepare_hub_release(pack, "acme/shop-pack").files}
        assert {"questions.jsonl", "certificate.json", "manifest.json", "verify.py",
                "rotations/seed-8/attestation.intoto.json",
                "rotations/seed-8/verify_attestation.py"} <= paths

    def test_the_card_names_the_pass_rule(self, pack):
        card = prepare_hub_release(pack, "acme/shop-pack").card
        assert "task_categories:\n- table-question-answering" in card
        assert "correct only when it returns the expected answer on all of them" in card
        assert "--candidates" in card

    def test_a_changed_rotation_is_refused(self, pack, tmp_path):
        copy = Path(shutil.copytree(pack, tmp_path / "pack"))
        target = copy / "rotations" / "seed-8" / "tables" / "customers.csv"
        target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with pytest.raises(PublishRefused) as caught:
            prepare_hub_release(copy, "acme/shop-pack")
        assert caught.value.verification_failed


class TestUpload:
    def test_one_commit_with_the_card_as_readme(self, dataset, monkeypatch):
        hub = pytest.importorskip("huggingface_hub")
        calls = {}

        class FakeApi:
            def create_repo(self, repo_id, **kwargs):
                calls["repo"] = (repo_id, kwargs)
                return f"https://huggingface.co/datasets/{repo_id}"

            def create_commit(self, repo_id, **kwargs):
                calls["commit"] = (repo_id, kwargs)

        monkeypatch.setattr(hub, "HfApi", FakeApi)
        release = prepare_hub_release(dataset, "acme/shop")
        url = publish_to_hub(release, private=True)

        assert url == "https://huggingface.co/datasets/acme/shop"
        assert calls["repo"] == ("acme/shop", {"repo_type": "dataset", "private": True,
                                               "exist_ok": True})
        operations = calls["commit"][1]["operations"]
        uploaded = {op.path_in_repo for op in operations}
        assert uploaded == set(release.to_dict()["files"])
        readme = next(op for op in operations if op.path_in_repo == "README.md")
        assert readme.path_or_fileobj == release.card.encode("utf-8")

    @pytest.mark.skipif(not os.environ.get("MISATA_HF_TEST_REPO"),
                        reason="set MISATA_HF_TEST_REPO and HF_TOKEN to publish for real")
    def test_publishes_to_a_private_repository(self, dataset):
        url = publish_to_hub(prepare_hub_release(dataset, os.environ["MISATA_HF_TEST_REPO"]),
                             private=True)
        assert os.environ["MISATA_HF_TEST_REPO"] in url


class TestCli:
    def test_dry_run_writes_the_card_and_uploads_nothing(self, dataset):
        result = CliRunner().invoke(
            main, ["publish", str(dataset), "--hf", "acme/shop", "--dry-run", "--json"])
        assert result.exit_code == 0, result.output
        envelope = json.loads(result.output)
        assert envelope["data"]["publish"]["dry_run"] is True
        assert (dataset / CARD_FILE).read_text(encoding="utf-8").startswith("---\nlicense:")

    def test_tampered_data_exits_failed(self, dataset):
        (dataset / "customers.csv").write_text("customer_id\n1\n", encoding="utf-8")
        result = CliRunner().invoke(main, ["publish", str(dataset), "--hf", "acme/shop",
                                           "--dry-run"])
        assert result.exit_code == 1

    def test_mimic_output_is_refused_without_consent(self, tmp_path):
        source = tmp_path / "people.csv"
        source.write_text("age,city\n31,Paris\n44,Lyon\n29,Nice\n", encoding="utf-8")
        out = tmp_path / "twin"
        runner = CliRunner()
        assert runner.invoke(main, ["mimic", str(source), "-o", str(out), "--seed", "1"]
                             ).exit_code == 0
        assert (out / FITTED_MARKER).is_file()
        result = runner.invoke(main, ["publish", str(out), "--hf", "acme/twin", "--dry-run"])
        assert result.exit_code == 2
        assert "--allow-fitted" in result.output


def test_the_spec_round_trips_through_the_dataset(dataset):
    """The published spec regenerates the published rows."""
    schema = load_yaml_schema(dataset / "misata.yaml")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        again = misata.generate_from_schema(schema)
    copy = dataset.parent / "again"
    copy.mkdir()
    save_yaml_schema(schema, copy / "misata.yaml")
    for name, df in again.items():
        df.to_csv(copy / f"{name}.csv", index=False)
    assert (copy / "orders.csv").read_bytes() == (dataset / "orders.csv").read_bytes()
