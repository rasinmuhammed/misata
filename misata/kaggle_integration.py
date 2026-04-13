"""
Kaggle vocabulary enrichment pipeline for Misata.

Downloads open-license datasets from Kaggle and extracts vocabulary
assets (names, companies, cities, job titles, etc.) into the local
``AssetStore``.  Once populated, the asset store is used automatically
during generation — text columns get real-world vocabulary without any
LLM calls.

Usage::

    import misata

    # One-time: download & index vocabulary for a domain
    result = misata.enrich_from_kaggle("ecommerce")
    print(result)
    # EnrichmentResult(domain='ecommerce', assets_added=4, datasets_ingested=1)

    # See what's already downloaded
    misata.kaggle_status()
    # AssetStore status (5 domains, 23 vocabulary assets):
    #   ecommerce/global : company_name (1240 values), product_name (843 values) ...
    #   saas/global      : person_name (3100 values) ...

    # Provide your own CSV if you already have the file
    misata.ingest_csv(
        csv_path="~/Downloads/companies.csv",
        domain="fintech",
        column_map={"Name": "company_name", "City": "city"},
        license_name="CC0-1.0",
    )

Requirements
------------
``pip install kaggle``

Credentials must be configured — one of:
- ``~/.kaggle/kaggle.json``  → ``{"username": "...", "key": "..."}``
- ``KAGGLE_USERNAME`` + ``KAGGLE_KEY`` environment variables
"""

from __future__ import annotations

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from misata.assets import (
    AssetStore,
    KaggleAssetIngestor,
    KaggleDatasetDescriptor,
    LicensePolicy,
    KaggleIngestionResult,
)
from misata.domain_capsule import AssetProvenance, VocabularyAsset


# ---------------------------------------------------------------------------
# Column name → semantic asset name heuristics
# ---------------------------------------------------------------------------

# Each key is a lower-cased, underscore-normalised column name.
# Values are the canonical asset names expected by SemanticVocabularyGenerator.
_COLUMN_ASSET_MAP: Dict[str, str] = {
    # Person names
    "name":             "person_name",
    "full_name":        "person_name",
    "customer_name":    "person_name",
    "user_name":        "person_name",
    "username":         "person_name",
    "author":           "person_name",
    "author_name":      "person_name",
    "player":           "person_name",
    "player_name":      "person_name",
    "employee":         "person_name",
    "employee_name":    "person_name",
    "contact":          "person_name",
    "contact_name":     "person_name",
    "first_name":       "first_name",
    "firstname":        "first_name",
    "fname":            "first_name",
    "given_name":       "first_name",
    "last_name":        "last_name",
    "lastname":         "last_name",
    "lname":            "last_name",
    "surname":          "last_name",
    "family_name":      "last_name",
    # Company / org
    "company":          "company_name",
    "company_name":     "company_name",
    "organization":     "company_name",
    "organisation":     "company_name",
    "employer":         "company_name",
    "brand":            "company_name",
    "merchant":         "company_name",
    "store":            "company_name",
    "vendor":           "company_name",
    "publisher":        "company_name",
    "institution":      "company_name",
    # Products
    "product":          "product_name",
    "product_name":     "product_name",
    "item_name":        "product_name",
    "item":             "product_name",
    "product_title":    "product_name",
    # Locations
    "city":             "city",
    "city_name":        "city",
    "town":             "city",
    "country":          "country",
    "country_name":     "country",
    "state":            "state",
    "province":         "state",
    "region":           "region",
    # Jobs
    "job":              "job_title",
    "job_title":        "job_title",
    "jobtitle":         "job_title",
    "position":         "job_title",
    "occupation":       "job_title",
    "role":             "job_title",
    "designation":      "job_title",
    "title":            "job_title",   # context-dependent; good enough as a hint
    # Healthcare
    "diagnosis":        "medical_condition",
    "condition":        "medical_condition",
    "disease":          "medical_condition",
    "medication":       "medication_name",
    "drug":             "medication_name",
    "drug_name":        "medication_name",
    "medicine":         "medication_name",
    # Finance
    "ticker":           "ticker_symbol",
    "symbol":           "ticker_symbol",
    "sector":           "industry_sector",
    "industry":         "industry_sector",
    # Misc text
    "category":         "category",
    "genre":            "genre",
    "skill":            "skill",
    "tag":              "tag",
    "keyword":          "keyword",
    "nationality":      "country",
}


def _normalise_col(col: str) -> str:
    return col.lower().strip().replace(" ", "_").replace("-", "_")


def detect_column_assets(columns: List[str]) -> Dict[str, str]:
    """Heuristically map CSV column names to Misata asset names.

    Args:
        columns: List of column headers from a CSV file.

    Returns:
        ``{csv_column: asset_name}`` dict (only columns with matches).

    Example::

        detect_column_assets(["Name", "Company", "City", "Revenue"])
        # {"Name": "person_name", "Company": "company_name", "City": "city"}
    """
    result: Dict[str, str] = {}
    for col in columns:
        key = _normalise_col(col)
        if key in _COLUMN_ASSET_MAP:
            result[col] = _COLUMN_ASSET_MAP[key]
    return result


# ---------------------------------------------------------------------------
# Curated dataset registry (CC0 / permissive only)
# ---------------------------------------------------------------------------

# Datasets that are well-known, stable, and permissively licensed.
# Ref format: "<owner>/<dataset-slug>" as used by the Kaggle Python API.
_CURATED_REGISTRY: Dict[str, List[KaggleDatasetDescriptor]] = {
    "ecommerce": [
        KaggleDatasetDescriptor(
            dataset_ref="olistbr/brazilian-ecommerce",
            title="Brazilian E-Commerce (Olist)",
            license_name="CC0-1.0",
            domain="ecommerce",
            attribution="Olist Store (CC0 1.0)",
            tags=["ecommerce", "orders", "customers", "products"],
        ),
        KaggleDatasetDescriptor(
            dataset_ref="carrie1/ecommerce-data",
            title="E-Commerce Data",
            license_name="CC0-1.0",
            domain="ecommerce",
            tags=["ecommerce", "products"],
        ),
    ],
    "saas": [
        KaggleDatasetDescriptor(
            dataset_ref="blastchar/telco-customer-churn",
            title="Telco Customer Churn",
            license_name="CC0-1.0",
            domain="saas",
            tags=["saas", "churn", "customers"],
        ),
    ],
    "fintech": [
        KaggleDatasetDescriptor(
            dataset_ref="ealaxi/paysim1",
            title="PaySim Mobile Money Transactions",
            license_name="CC0-1.0",
            domain="fintech",
            tags=["fintech", "transactions", "fraud"],
        ),
    ],
    "healthcare": [
        KaggleDatasetDescriptor(
            dataset_ref="nehaprabhavalkar/iv-health-data",
            title="Hospital Patient Records",
            license_name="CC0-1.0",
            domain="healthcare",
            tags=["healthcare", "patients"],
        ),
    ],
    "logistics": [
        KaggleDatasetDescriptor(
            dataset_ref="olistbr/brazilian-ecommerce",
            title="Brazilian E-Commerce (Olist) — Logistics",
            license_name="CC0-1.0",
            domain="logistics",
            tags=["logistics", "orders", "shipping"],
        ),
    ],
    "marketplace": [
        KaggleDatasetDescriptor(
            dataset_ref="olistbr/brazilian-ecommerce",
            title="Brazilian E-Commerce Marketplace (Olist)",
            license_name="CC0-1.0",
            domain="marketplace",
            tags=["marketplace", "vendors", "products"],
        ),
    ],
    "generic": [
        KaggleDatasetDescriptor(
            dataset_ref="datasnaek/youtube-new",
            title="Trending YouTube Video Statistics",
            license_name="CC0-1.0",
            domain="generic",
            tags=["generic", "text", "titles"],
        ),
    ],
}


# ---------------------------------------------------------------------------
# Return types
# ---------------------------------------------------------------------------

@dataclass
class EnrichmentResult:
    """Summary of a ``enrich_from_kaggle()`` run."""

    domain: str
    datasets_ingested: int = 0
    assets_added: int = 0
    skipped: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        status = "ok" if not self.errors else f"{len(self.errors)} error(s)"
        skipped = f", {len(self.skipped)} skipped" if self.skipped else ""
        return (
            f"EnrichmentResult(domain={self.domain!r}, "
            f"datasets_ingested={self.datasets_ingested}, "
            f"assets_added={self.assets_added}{skipped}, "
            f"status={status!r})"
        )


# ---------------------------------------------------------------------------
# Kaggle API helper
# ---------------------------------------------------------------------------

def _get_kaggle_api() -> Optional[Any]:
    """Return an authenticated KaggleApiExtended, or None if unavailable."""
    try:
        from kaggle.api.kaggle_api_extended import KaggleApiExtended  # type: ignore
        api = KaggleApiExtended()
        api.authenticate()
        return api
    except ImportError:
        return None
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core enrichment function
# ---------------------------------------------------------------------------

def enrich_from_kaggle(
    domain: str,
    *,
    asset_store_dir: Optional[str] = None,
    license_policy: Optional[LicensePolicy] = None,
    max_rows: int = 50_000,
    overwrite: bool = False,
) -> EnrichmentResult:
    """Download Kaggle vocabulary assets for a domain and persist them locally.

    The downloaded vocabulary is stored in ``~/.misata/assets/`` and used
    automatically by Misata's text generators in subsequent ``generate()``
    calls — no further action required.

    Requires the ``kaggle`` package and valid Kaggle credentials.

    Args:
        domain:          One of: ``ecommerce``, ``saas``, ``fintech``,
                         ``healthcare``, ``logistics``, ``marketplace``,
                         or any free-text domain keyword.
        asset_store_dir: Override the default ``~/.misata/assets`` directory.
        license_policy:  Custom :class:`LicensePolicy`.  Defaults to the
                         built-in CC0-permissive policy.
        max_rows:        Cap on rows read per CSV file (default 50 000).
        overwrite:       Re-download even when assets for the domain exist.

    Returns:
        :class:`EnrichmentResult` — check ``.assets_added`` and ``.errors``.

    Example::

        result = misata.enrich_from_kaggle("ecommerce")
        print(result)
        # EnrichmentResult(domain='ecommerce', datasets_ingested=1, assets_added=3, status='ok')

        # Now generate — city / company names come from real-world data
        tables = misata.generate("An ecommerce store with 5k orders")
    """
    result = EnrichmentResult(domain=domain)
    policy = license_policy or LicensePolicy()
    store = AssetStore(root_dir=asset_store_dir)
    ingestor = KaggleAssetIngestor(asset_store=store, license_policy=policy)

    # Skip if assets already exist and overwrite=False
    if not overwrite:
        existing = store.load_vocabulary("company_name", domain=domain)
        existing += store.load_vocabulary("person_name", domain=domain)
        existing += store.load_vocabulary("city", domain=domain)
        if existing:
            return result  # already enriched

    api = _get_kaggle_api()
    if api is None:
        result.errors.append(
            "Kaggle package not installed or credentials not configured. "
            "Run: pip install kaggle  and set up ~/.kaggle/kaggle.json"
        )
        return result

    # Gather candidates: curated list first, then live search
    candidates: List[KaggleDatasetDescriptor] = list(
        _CURATED_REGISTRY.get(domain, _CURATED_REGISTRY.get("generic", []))
    )

    # Live search to supplement curated list (best-effort)
    try:
        live = api.dataset_list(search=domain, sort_by="votes", file_type="csv")
        for item in (live or [])[:3]:
            license_name = getattr(item, "licenseName", "") or ""
            if policy.is_allowed(license_name):
                desc = KaggleDatasetDescriptor(
                    dataset_ref=str(item.ref),
                    title=str(item.title),
                    license_name=license_name,
                    domain=domain,
                )
                # Avoid duplicating curated entries
                curated_refs = {c.dataset_ref for c in candidates}
                if desc.dataset_ref not in curated_refs:
                    candidates.append(desc)
    except Exception:
        pass  # live search is best-effort

    if not candidates:
        result.errors.append(f"No CC0/permissive datasets found for domain '{domain}'.")
        return result

    # Download and ingest
    tmpdir = tempfile.mkdtemp(prefix="misata_kaggle_")
    try:
        for descriptor in candidates[:2]:  # cap at 2 downloads per call
            if not policy.is_allowed(descriptor.license_name):
                result.skipped.append(
                    f"{descriptor.dataset_ref} ({descriptor.license_name})"
                )
                continue
            try:
                dl_path = Path(tmpdir) / descriptor.dataset_ref.replace("/", "_")
                dl_path.mkdir(parents=True, exist_ok=True)
                api.dataset_download_files(
                    descriptor.dataset_ref,
                    path=str(dl_path),
                    unzip=True,
                    quiet=True,
                )
                csv_files = sorted(dl_path.rglob("*.csv"))
                if not csv_files:
                    result.skipped.append(
                        f"{descriptor.dataset_ref}: no CSV files found after download"
                    )
                    continue
                for csv_file in csv_files[:3]:   # at most 3 CSVs per dataset
                    col_map = _auto_map_csv(csv_file, max_rows=max_rows)
                    if not col_map:
                        continue
                    ingestion: KaggleIngestionResult = ingestor.ingest_csv(
                        descriptor=descriptor,
                        csv_path=str(csv_file),
                        column_to_asset=col_map,
                        limit=max_rows,
                        dedupe=True,
                    )
                    if ingestion.accepted:
                        result.assets_added += ingestion.assets_written
                result.datasets_ingested += 1
            except Exception as exc:
                result.errors.append(f"{descriptor.dataset_ref}: {exc}")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    return result


def _auto_map_csv(csv_path: Path, max_rows: int = 100) -> Dict[str, str]:
    """Read CSV header and return column→asset mapping via heuristics."""
    import csv as _csv
    try:
        with csv_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = _csv.DictReader(fh)
            columns = reader.fieldnames or []
    except Exception:
        return {}
    return detect_column_assets(list(columns))


# ---------------------------------------------------------------------------
# Manual ingest helper
# ---------------------------------------------------------------------------

def ingest_csv(
    csv_path: str,
    domain: str,
    column_map: Dict[str, str],
    *,
    license_name: str = "CC0-1.0",
    attribution: Optional[str] = None,
    asset_store_dir: Optional[str] = None,
    max_rows: int = 100_000,
    dedupe: bool = True,
) -> KaggleIngestionResult:
    """Import a local CSV file into the Misata asset store.

    Use this when you already have a CSV file and want to add its vocabulary
    to Misata without going through the Kaggle API.

    Args:
        csv_path:         Absolute or ``~/`` path to the CSV file.
        domain:           Domain tag (e.g. ``"ecommerce"``).
        column_map:       ``{csv_column: asset_name}`` mapping.
                          Asset names: ``person_name``, ``company_name``,
                          ``city``, ``product_name``, ``job_title``, etc.
        license_name:     SPDX license ID for provenance.
        attribution:      Optional attribution text.
        asset_store_dir:  Override default ``~/.misata/assets``.
        max_rows:         Cap on rows read.
        dedupe:           Remove duplicate values before saving.

    Returns:
        :class:`~misata.assets.KaggleIngestionResult`

    Example::

        result = misata.ingest_csv(
            "~/data/companies.csv",
            domain="fintech",
            column_map={"CompanyName": "company_name", "City": "city"},
        )
        print(result.assets_written)  # 2
    """
    store = AssetStore(root_dir=asset_store_dir)
    policy = LicensePolicy(allowed={license_name})
    ingestor = KaggleAssetIngestor(asset_store=store, license_policy=policy)
    descriptor = KaggleDatasetDescriptor(
        dataset_ref=str(csv_path),
        title=Path(csv_path).name,
        license_name=license_name,
        attribution=attribution,
        domain=domain,
    )
    return ingestor.ingest_csv(
        descriptor=descriptor,
        csv_path=csv_path,
        column_to_asset=column_map,
        limit=max_rows,
        dedupe=dedupe,
    )


# ---------------------------------------------------------------------------
# Status / inspection
# ---------------------------------------------------------------------------

def kaggle_status(asset_store_dir: Optional[str] = None) -> str:
    """Print a summary of locally stored vocabulary assets.

    Returns a formatted string listing all domains and their vocabulary
    collections with value counts.

    Args:
        asset_store_dir: Override default ``~/.misata/assets``.

    Returns:
        Human-readable status string.

    Example::

        print(misata.kaggle_status())
        # AssetStore status (2 domains, 7 vocabulary assets):
        #   ecommerce / global
        #     company_name  :  1 240 values
        #     product_name  :    843 values
        #   generic / global
        #     person_name   :  3 100 values
        #     city          :  5 230 values
    """
    store = AssetStore(root_dir=asset_store_dir)
    root = store.root

    if not root.exists():
        return "AssetStore is empty — run misata.enrich_from_kaggle(domain) to populate."

    total_domains = 0
    total_assets = 0
    lines: List[str] = []

    for domain_dir in sorted(root.iterdir()):
        if not domain_dir.is_dir():
            continue
        for locale_dir in sorted(domain_dir.iterdir()):
            if not locale_dir.is_dir():
                continue
            json_files = list(locale_dir.glob("*.json"))
            if not json_files:
                continue
            total_domains += 1
            lines.append(f"  {domain_dir.name} / {locale_dir.name}")
            for jf in sorted(json_files):
                try:
                    import json as _json
                    payload = _json.loads(jf.read_text(encoding="utf-8"))
                    count = len(payload.get("values", []))
                    total_assets += 1
                    lines.append(f"    {jf.stem:<20s}: {count:>6,} values")
                except Exception:
                    lines.append(f"    {jf.stem} (unreadable)")

    if not lines:
        return "AssetStore is empty — run misata.enrich_from_kaggle(domain) to populate."

    header = f"AssetStore status ({total_domains} scope(s), {total_assets} vocabulary asset(s)):"
    return "\n".join([header] + lines)


# ---------------------------------------------------------------------------
# Search-only (no download)
# ---------------------------------------------------------------------------

def kaggle_find(domain: str, max_results: int = 5) -> List[KaggleDatasetDescriptor]:
    """Search Kaggle for datasets matching a domain without downloading.

    Returns a list of candidates (curated + live search).  Useful for
    previewing what would be ingested by :func:`enrich_from_kaggle`.

    Args:
        domain:      Domain keyword (e.g. ``"healthcare"``, ``"logistics"``).
        max_results: Maximum number of candidates to return.

    Returns:
        List of :class:`~misata.assets.KaggleDatasetDescriptor` objects.

    Example::

        for ds in misata.kaggle_find("healthcare"):
            print(ds.dataset_ref, ds.license_name)
    """
    policy = LicensePolicy()
    results: List[KaggleDatasetDescriptor] = list(
        _CURATED_REGISTRY.get(domain, _CURATED_REGISTRY.get("generic", []))
    )

    api = _get_kaggle_api()
    if api is not None:
        try:
            live = api.dataset_list(search=domain, sort_by="votes", file_type="csv")
            curated_refs = {c.dataset_ref for c in results}
            for item in (live or [])[:max_results]:
                license_name = getattr(item, "licenseName", "") or ""
                if policy.is_allowed(license_name):
                    desc = KaggleDatasetDescriptor(
                        dataset_ref=str(item.ref),
                        title=str(item.title),
                        license_name=license_name,
                        domain=domain,
                    )
                    if desc.dataset_ref not in curated_refs:
                        results.append(desc)
        except Exception:
            pass

    return results[:max_results]
