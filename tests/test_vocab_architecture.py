"""0.8.1.24: vocabulary architecture — validator, Wikidata builder (mocked),
conditional capsules, bundled registry auto-attach, TPM-fit retry."""
import json

import numpy as np
import pandas as pd
import pytest

import misata
from misata.vocab_validator import validate_vocabulary
from misata.domain_capsule import AssetProvenance, DomainCapsule, VocabularyAsset
from misata.capsules import load_capsule, merge_into, save_capsule


class TestValidator:
    def test_rejects_placeholders_and_filler(self):
        r = validate_vocabulary([
            "John Doe", "Jane Smith", "Value A", "Item 12", "Q1636652",
            "Rolex Submariner", "Peregrine Falcon", "TBD", "",
        ])
        assert r.accepted == ["Rolex Submariner", "Peregrine Falcon"]
        reasons = {reason for _, reason in r.rejected}
        assert "placeholder" in reasons and "enumerated-filler" in reasons
        assert "unlabeled-entity" in reasons

    def test_rejects_sentences_keeps_multiword_labels(self):
        r = validate_vocabulary([
            "Wheelchair Accessible", "Sporting Event",
            "The customer requested a follow-up call about the invoice.",
        ])
        assert "Wheelchair Accessible" in r.accepted
        assert "Sporting Event" in r.accepted
        assert len(r.rejected) == 1

    def test_dedupes_case_insensitively(self):
        r = validate_vocabulary(["Rolex", "rolex", "ROLEX", "Omega"])
        assert r.accepted == ["Rolex", "Omega"]


class TestWikidataBuilderMocked:
    def test_capsule_from_wikidata_conditional(self, monkeypatch):
        import misata.wikidata as wd
        monkeypatch.setattr(wd, "fetch_conditional_members", lambda *a, **k: {
            "Rolex": ["Rolex Submariner", "Rolex Datejust", "Q999"],
            "Patek Philippe": ["Nautilus", "Calatrava"],
            "John Doe": ["Something"],  # placeholder parent must be dropped
        })
        capsule = wd.capsule_from_wikidata(
            domain="watches", column="model", class_qid="Q178794",
            conditional_property="P176", parent_column="brand",
        )
        cmap = capsule.conditional_vocabularies["model"]["map"]
        assert set(cmap) == {"Rolex", "Patek Philippe"}
        assert "Q999" not in cmap["Rolex"], "QID labels must be validated out"
        provs = capsule.provenance["model"]
        assert provs[0].source_type == "wikidata"
        assert provs[0].license_name == "CC0-1.0"

    def test_capsule_from_wikidata_flat_validates(self, monkeypatch):
        import misata.wikidata as wd
        monkeypatch.setattr(wd, "fetch_class_members",
                            lambda *a, **k: ["Peregrine Falcon", "Gyrfalcon", "Q123", "test"])
        capsule = wd.capsule_from_wikidata(domain="falconry", column="species",
                                           class_qid="Q43489")
        assert capsule.vocabularies["species"] == ["Peregrine Falcon", "Gyrfalcon"]

    def test_too_few_values_raises(self, monkeypatch):
        import misata.wikidata as wd
        monkeypatch.setattr(wd, "fetch_class_members", lambda *a, **k: ["Q1", "Q2"])
        with pytest.raises(ValueError):
            wd.capsule_from_wikidata(domain="x", column="y", class_qid="Q1")


class TestConditionalCapsules:
    def test_capsule_round_trip_preserves_conditional(self, tmp_path):
        c = DomainCapsule(domain="watches")
        c.conditional_vocabularies["model"] = {
            "parent": "brand", "map": {"Rolex": ["Submariner", "Datejust"]}}
        c.record_asset(VocabularyAsset(
            name="brand", values=["Rolex"],
            provenance=AssetProvenance("curated", "test", "CC0-1.0")))
        p = save_capsule(c, tmp_path / "w.capsule.json")
        loaded = load_capsule(p)
        assert loaded.conditional_vocabularies["model"]["map"]["Rolex"] == [
            "Submariner", "Datejust"]

    def test_merge_carries_conditional(self):
        base = DomainCapsule(domain="base")
        overlay = DomainCapsule(domain="over")
        overlay.conditional_vocabularies["model"] = {
            "parent": "brand", "map": {"Rolex": ["Submariner"]}}
        merge_into(base, overlay)
        assert "model" in base.conditional_vocabularies


class TestRegistryAutoAttach:
    def _watch_schema(self, table_name="watches"):
        return misata.from_dict_schema({
            "name": "auction",
            "tables": {
                table_name: {"__rows__": 40,
                    "id": {"type": "integer", "primary_key": True},
                    "brand": {"type": "string"},
                    "model_name": {"type": "string"}},
            },
        }, seed=5)

    def test_watch_schema_gets_real_brands_and_coherent_models(self):
        tables = misata.generate_from_schema(self._watch_schema())
        w = tables["watches"]
        from misata.capsule_registry import load_registry_capsule
        cmap = load_registry_capsule("vintage-watches").conditional_vocabularies["model_name"]["map"]
        assert set(w["brand"]) <= set(cmap), set(w["brand"])
        ok = sum(str(m) in cmap[str(b)] for b, m in zip(w["brand"], w["model_name"]))
        assert ok == len(w), f"only {ok}/{len(w)} brand-model pairs coherent"

    def test_keyword_gate_blocks_unrelated_tables(self):
        # products with brand+model must NOT get watch vocabulary.
        schema = self._watch_schema(table_name="products")
        from misata.capsule_registry import match_registry_capsules
        assert "vintage-watches" not in match_registry_capsules(schema)

    def test_falconry_species_attach(self):
        tables = misata.generate_from_schema(misata.from_dict_schema({
            "name": "falconry club",
            "tables": {"birds": {"__rows__": 30,
                "id": {"type": "integer", "primary_key": True},
                "species": {"type": "string"}}},
        }, seed=3))
        from misata.capsule_registry import load_registry_capsule
        pool = set(load_registry_capsule("falconry").vocabularies["species"])
        assert set(tables["birds"]["species"]) <= pool

    def test_registry_install(self, tmp_path):
        from misata.capsule_registry import install_capsule
        dest = install_capsule("vintage-watches", dest_dir=tmp_path)
        assert dest.exists()
        assert load_capsule(dest).conditional_vocabularies


class TestTpmFitRetry:
    def test_413_shrinks_max_tokens_and_retries(self, monkeypatch):
        from misata.llm_parser import LLMSchemaGenerator
        gen = LLMSchemaGenerator.__new__(LLMSchemaGenerator)
        gen._protocol = "openai"
        calls = []

        def fake_call(messages, max_tokens, temperature):
            calls.append(max_tokens)
            if len(calls) == 1:
                raise RuntimeError(
                    "Error code: 413 - Request too large for model x "
                    "on tokens per minute (TPM): Limit 8000, Requested 12114")
            return '{"ok": true}'

        monkeypatch.setattr(gen, "_call_openai_compatible", fake_call)
        out = gen._call_api([{"role": "user", "content": "hi"}], max_tokens=6000)
        assert out == '{"ok": true}'
        assert len(calls) == 2
        # prompt = 12114-6000 = 6114; fitted = 8000-6114-200 = 1686
        assert calls[1] == 1686


class TestTableLevelVocabulary:
    def test_table_dunder_vocabulary_reaches_engine(self):
        tables = misata.generate_from_schema(misata.from_dict_schema({
            "reefs": {"__rows__": 50,
                "__vocabulary__": {"zone_name": ["Fore reef", "Back reef", "Reef crest"]},
                "id": {"type": "integer", "primary_key": True},
                "zone_name": {"type": "string"}},
        }, seed=2))
        assert set(tables["reefs"]["zone_name"]) <= {"Fore reef", "Back reef", "Reef crest"}


class TestAutoDiscovery:
    def _config(self, table="synthesizers", column="model"):
        return misata.from_dict_schema({
            "name": "vintage synth collection",
            "tables": {table: {"__rows__": 20,
                "id": {"type": "integer", "primary_key": True},
                column: {"type": "string"}}},
        }, seed=1)

    def test_discovery_attaches_verified_vocabulary(self, monkeypatch, tmp_path):
        import misata.vocab_discovery as vd
        monkeypatch.setattr(vd, "_CACHE_PATH", tmp_path / "cache.json")
        monkeypatch.setattr(vd, "_search_candidates", lambda term: [
            {"qid": "Q163829", "label": "synthesizer", "description": "electronic instrument"}])
        import misata.wikidata as wd
        monkeypatch.setattr(wd, "fetch_class_members", lambda qid, limit=120: [
            "Minimoog", "Roland Juno-106", "Yamaha DX7", "ARP 2600",
            "Sequential Prophet-5", "Korg MS-20", "Oberheim OB-Xa",
            "Roland TB-303", "Moog Voyager", "EMS VCS 3"])
        cfg = self._config()
        report = vd.enrich_schema_vocabulary(cfg, sparql_pause=0)
        assert report and report[0].attached
        assert report[0].qid == "Q163829"
        assert "model" in cfg.vocabularies
        assert "Yamaha DX7" in cfg.vocabularies["model"]

    def test_wrong_kind_candidates_rejected_by_description(self, monkeypatch, tmp_path):
        import misata.vocab_discovery as vd
        monkeypatch.setattr(vd, "_CACHE_PATH", tmp_path / "cache.json")
        raw_hits = [
            {"id": "Q1", "label": "Falcon", "description": "family name"},
            {"id": "Q2", "label": "Falcon", "description": "1978 studio album"},
        ]
        import urllib.request

        class FakeResp:
            def __init__(self, payload): self.payload = payload
            def read(self): import json as j; return j.dumps(self.payload).encode()
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(urllib.request, "urlopen",
                            lambda req, timeout=30: FakeResp({"search": raw_hits}))
        assert vd._search_candidates("falcon") == []

    def test_insufficient_values_not_attached(self, monkeypatch, tmp_path):
        import misata.vocab_discovery as vd
        monkeypatch.setattr(vd, "_CACHE_PATH", tmp_path / "cache.json")
        monkeypatch.setattr(vd, "_search_candidates", lambda term: [
            {"qid": "Q9", "label": "thing", "description": "a class"}])
        import misata.wikidata as wd
        monkeypatch.setattr(wd, "fetch_class_members", lambda qid, limit=120: ["Q1", "Q2", "One"])
        cfg = self._config()
        report = vd.enrich_schema_vocabulary(cfg, sparql_pause=0)
        assert report and not report[0].attached

    def test_registry_covered_columns_skipped(self, monkeypatch, tmp_path):
        import misata.vocab_discovery as vd
        monkeypatch.setattr(vd, "_CACHE_PATH", tmp_path / "cache.json")
        called = []
        monkeypatch.setattr(vd, "discover_column",
                            lambda *a, **k: called.append(a) or vd.Discovery("x", "y"))
        cfg = misata.from_dict_schema({
            "name": "falconry club",
            "tables": {"birds": {"__rows__": 10,
                "id": {"type": "integer", "primary_key": True},
                "species": {"type": "string"}}},
        }, seed=2)
        vd.enrich_schema_vocabulary(cfg, sparql_pause=0)
        assert called == [], "registry-covered species column must not trigger discovery"

    def test_cache_hit_short_circuits_network(self, monkeypatch, tmp_path):
        import misata.vocab_discovery as vd
        import json as j
        cache_file = tmp_path / "cache.json"
        cache_file.write_text(j.dumps({"vintage synth model": {
            "qid": "Q163829", "label": "synthesizer",
            "values": ["Minimoog", "Yamaha DX7"]}}))
        monkeypatch.setattr(vd, "_CACHE_PATH", cache_file)
        monkeypatch.setattr(vd, "_search_candidates",
                            lambda term: (_ for _ in ()).throw(AssertionError("network hit")))
        d = vd.discover_column("synths", "model", domain_hint="vintage synths")
        assert d.attached and d.values == ["Minimoog", "Yamaha DX7"]
