import csv

from misata.assets import AssetStore, KaggleAssetIngestor, KaggleDatasetDescriptor, LicensePolicy
from misata.schema import Column, RealismConfig, SchemaConfig, Table
from misata.simulator import DataSimulator
from misata.vocabulary import SemanticVocabularyGenerator


def test_asset_store_round_trip(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    descriptor = KaggleDatasetDescriptor(
        dataset_ref="demo/names",
        title="Demo Names",
        license_name="CC0-1.0",
        domain="generic",
        locale="ja_JP",
    )

    csv_path = tmp_path / "names.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["first_name"])
        writer.writeheader()
        writer.writerow({"first_name": "Hana"})
        writer.writerow({"first_name": "Sora"})

    ingestor = KaggleAssetIngestor(store)
    result = ingestor.ingest_csv(descriptor, str(csv_path), {"first_name": "first_name"})

    assert result.accepted is True
    assets = store.load_vocabulary("first_name", domain="generic", locale="ja_JP")
    assert len(assets) == 1
    assert assets[0].values == ["Hana", "Sora"]
    assert assets[0].provenance.license_name == "CC0-1.0"


def test_kaggle_ingestion_blocks_restricted_license(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    descriptor = KaggleDatasetDescriptor(
        dataset_ref="demo/restricted",
        title="Restricted",
        license_name="CC-BY-NC-4.0",
    )
    csv_path = tmp_path / "restricted.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name"])
        writer.writeheader()
        writer.writerow({"name": "ShouldNotImport"})

    ingestor = KaggleAssetIngestor(store, license_policy=LicensePolicy())
    result = ingestor.ingest_csv(descriptor, str(csv_path), {"name": "first_name"})

    assert result.accepted is False
    assert "blocked" in (result.reason or "").lower()
    assert store.load_vocabulary("first_name") == []


def test_semantic_vocabulary_generator_prefers_asset_store(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    descriptor = KaggleDatasetDescriptor(
        dataset_ref="demo/company",
        title="Companies",
        license_name="CC0-1.0",
        domain="saas",
        locale="global",
    )
    csv_path = tmp_path / "companies.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["company"])
        writer.writeheader()
        writer.writerow({"company": "Shinrai Systems"})
        writer.writerow({"company": "Sakura Cloudworks"})

    KaggleAssetIngestor(store).ingest_csv(descriptor, str(csv_path), {"company": "company_name"})

    schema = SchemaConfig(
        name="SaaS",
        tables=[Table(name="users", row_count=5)],
        columns={"users": [Column(name="company", type="text", distribution_params={})]},
        realism=RealismConfig(domain_hint="saas", asset_store_dir=str(tmp_path / "assets")),
    )

    capsule = SemanticVocabularyGenerator(asset_store=store).build_capsule(schema)

    assert capsule.domain == "saas"
    assert capsule.get_values("company_name")[:2] == ["Shinrai Systems", "Sakura Cloudworks"]


def test_simulator_uses_asset_backed_vocabularies(tmp_path):
    store = AssetStore(str(tmp_path / "assets"))
    descriptor = KaggleDatasetDescriptor(
        dataset_ref="demo/japanese-names",
        title="Japanese Names",
        license_name="CC0-1.0",
        domain="generic",
        locale="ja_JP",
    )
    csv_path = tmp_path / "jp_names.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["first_name", "last_name"])
        writer.writeheader()
        writer.writerow({"first_name": "Hana", "last_name": "Sato"})
        writer.writerow({"first_name": "Sora", "last_name": "Tanaka"})

    ingestor = KaggleAssetIngestor(store)
    ingestor.ingest_csv(descriptor, str(csv_path), {"first_name": "first_name", "last_name": "last_name"})

    schema = SchemaConfig(
        name="Localized",
        seed=42,
        tables=[Table(name="users", row_count=10)],
        columns={
            "users": [
                Column(name="id", type="int", distribution_params={"distribution": "uniform", "min": 1, "max": 10}, unique=True),
                Column(name="first_name", type="text", distribution_params={}),
                Column(name="last_name", type="text", distribution_params={}),
            ]
        },
        realism=RealismConfig(
            text_mode="realistic_catalog",
            locale="ja_JP",
            asset_store_dir=str(tmp_path / "assets"),
        ),
    )

    simulator = DataSimulator(schema)
    rows = next(simulator.generate_batches("users"))

    assert set(rows["first_name"].unique()).issubset({"Hana", "Sora"})
    assert set(rows["last_name"].unique()).issubset({"Sato", "Tanaka"})
