"""Tests for the capsule registry: shareable domain vocabulary packs.

Intelligence is spent once (mining example data, or an LLM call); the file
is reviewable and versionable; generation stays deterministic and offline.
"""

import json
import warnings

import pandas as pd
import pytest

import misata
from misata.capsules import (
    capsule_from_dataframes,
    capsule_from_llm,
    load_capsule,
    merge_into,
    save_capsule,
)
from misata.domain_capsule import DomainCapsule


@pytest.fixture
def vet_frames():
    return {
        "patients": pd.DataFrame(
            {
                "patient_id": range(8),
                "species": ["Dog", "Cat", "Dog", "Rabbit", "Cat", "Dog", "Parrot", "Cat"],
                "breed": ["Labrador", "Siamese", "Beagle", "Lop", "Persian", "Poodle", "Macaw", "Maine Coon"],
                "owner_email": ["a@x.com"] * 8,
                "visit_date": ["2024-01-01"] * 8,
                "weight_kg": [12.0, 4.1, 9.8, 1.9, 3.8, 7.2, 0.9, 4.4],
            }
        )
    }


class TestMining:
    def test_string_columns_become_vocabularies(self, vet_frames):
        capsule = capsule_from_dataframes("veterinary", vet_frames)
        assert set(capsule.vocabularies["species"]) == {"Dog", "Cat", "Rabbit", "Parrot"}
        assert len(capsule.vocabularies["breed"]) == 8

    def test_identity_and_numeric_columns_are_skipped(self, vet_frames):
        capsule = capsule_from_dataframes("veterinary", vet_frames)
        for excluded in ("patient_id", "owner_email", "visit_date", "weight_kg"):
            assert excluded not in capsule.vocabularies

    def test_provenance_records_source_column(self, vet_frames):
        capsule = capsule_from_dataframes("veterinary", vet_frames)
        prov = capsule.provenance["species"][0]
        assert prov.source_type == "mined_dataframe"
        assert prov.source_name == "patients.species"


class TestRoundTrip:
    def test_save_load_preserves_everything(self, vet_frames, tmp_path):
        capsule = capsule_from_dataframes("veterinary", vet_frames)
        path = save_capsule(capsule, tmp_path / "vet.capsule.json")
        loaded = load_capsule(path)
        assert loaded.domain == "veterinary"
        assert loaded.vocabularies == capsule.vocabularies
        assert loaded.provenance["species"][0].source_name == "patients.species"

    def test_file_is_plain_reviewable_json(self, vet_frames, tmp_path):
        path = save_capsule(capsule_from_dataframes("veterinary", vet_frames), tmp_path / "v.json")
        raw = json.loads(path.read_text())
        assert raw["misata_capsule"] == 1
        assert "species" in raw["vocabularies"]

    def test_non_capsule_file_is_rejected(self, tmp_path):
        bad = tmp_path / "x.json"
        bad.write_text('{"hello": 1}')
        with pytest.raises(ValueError, match="not a Misata capsule"):
            load_capsule(bad)

    def test_hand_written_capsule_without_provenance_loads(self, tmp_path):
        path = tmp_path / "hand.json"
        path.write_text(json.dumps({
            "misata_capsule": 1,
            "domain": "space",
            "vocabularies": {"rocket": ["Falcon", "Ariane", "Soyuz"]},
        }))
        loaded = load_capsule(path)
        assert loaded.vocabularies["rocket"] == ["Falcon", "Ariane", "Soyuz"]


class TestGenerationHookup:
    def _schema(self):
        return misata.from_dict_schema({
            "animals": {
                "id": {"type": "integer", "primary_key": True},
                "species": {"type": "string"},
                "breed": {"type": "string"},
            },
        }, row_count=60, seed=3)

    def test_capsule_vocab_drives_matching_columns(self, vet_frames, tmp_path):
        path = save_capsule(capsule_from_dataframes("veterinary", vet_frames), tmp_path / "v.json")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate_from_schema(self._schema(), capsule=str(path))
        assert set(tables["animals"]["species"]) <= {"Dog", "Cat", "Rabbit", "Parrot"}
        assert set(tables["animals"]["breed"]) <= set(vet_frames["patients"]["breed"])

    def test_without_capsule_columns_fall_back(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate_from_schema(self._schema())
        # no capsule: species column is NOT confined to the vet vocabulary
        assert not set(tables["animals"]["species"]) <= {"Dog", "Cat", "Rabbit", "Parrot"}

    def test_generate_story_accepts_capsule(self, vet_frames, tmp_path):
        path = save_capsule(capsule_from_dataframes("veterinary", vet_frames), tmp_path / "v.json")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tables = misata.generate(
                "A lab cataloguing 50 species and breeds", seed=1, capsule=str(path)
            )
        # composed/record tables exist and generation did not error
        assert tables

    def test_deterministic_under_seed(self, vet_frames, tmp_path):
        path = save_capsule(capsule_from_dataframes("veterinary", vet_frames), tmp_path / "v.json")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            a = misata.generate_from_schema(self._schema(), capsule=str(path))
            b = misata.generate_from_schema(self._schema(), capsule=str(path))
        assert list(a["animals"]["breed"]) == list(b["animals"]["breed"])


class TestMergeAndLLMPath:
    def test_merge_overlay_wins(self):
        base = DomainCapsule(domain="x", vocabularies={"species": ["Old"]})
        overlay = DomainCapsule(domain="y", vocabularies={"species": ["New"]})
        merged = merge_into(base, overlay)
        assert merged.vocabularies["species"] == ["New"]

    def test_llm_path_falls_back_to_curated_pools_without_key(self):
        # use_llm=True with no API key must not fail — curated pools serve.
        capsule = capsule_from_llm("healthcare", ["disease"], use_llm=False)
        assert len(capsule.vocabularies.get("disease", [])) > 10
