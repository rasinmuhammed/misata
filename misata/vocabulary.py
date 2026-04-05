"""Semantic vocabulary compilation for asset-backed realism."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Set

from misata.assets import AssetStore
from misata.domain_capsule import AssetProvenance, DomainCapsule, VocabularyAsset
from misata.reference_data import detect_domain as detect_reference_domain


DEFAULT_VOCABULARIES: Dict[str, List[str]] = {
    "first_name": [
        "James", "Mary", "Robert", "Patricia", "John", "Jennifer", "Michael", "Linda",
        "Aisha", "Priya", "Arjun", "Noah", "Emma", "Olivia", "Sophia", "Ethan",
    ],
    "last_name": [
        "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis",
        "Patel", "Singh", "Khan", "Nguyen", "Kim", "Wilson", "Clark", "Lewis",
    ],
    "company_name": [
        "Atlas Systems", "Blue Peak Labs", "North Summit Group", "Modern Vertex Solutions",
        "Prime Analytics Co", "Nova Commerce Collective",
    ],
    "job_title": [
        "Software Engineer", "Product Manager", "Customer Success Manager", "Data Analyst",
        "Engineering Manager", "Director of Sales", "Operations Manager", "Chief Technology Officer",
    ],
    "country": ["United States", "United Kingdom", "Canada", "Germany", "India"],
    "state": ["California", "Texas", "New York", "England", "Ontario", "Bavaria", "Maharashtra"],
    "city": ["New York", "London", "Toronto", "Berlin", "Mumbai", "Austin", "Seattle"],
    "product_name": [
        "Wireless Bluetooth Headphones Pro", "Classic Oxford Shirt", "Cast Iron Skillet",
        "Resistance Bands Set", "Designing Data-Intensive Applications",
    ],
    "product_description": [
        "Designed for everyday use with reliable performance and clean design.",
        "Built for teams that want quality, durability, and fast setup.",
        "Combines premium materials with practical features for daily use.",
    ],
}

DOMAIN_SPECIFIC_DEFAULTS: Dict[str, Dict[str, List[str]]] = {
    "ecommerce": {
        "product_name": ["Wireless Headphones", "Smart Watch", "Cotton T-Shirt", "Running Shoes", "Yoga Mat"],
        "company_name": ["Acme Retail", "Bright Cart", "Northline Commerce", "Blue Harbor Goods"],
    },
    "saas": {
        "job_title": ["Software Engineer", "Product Manager", "Customer Success Manager", "VP Engineering"],
        "company_name": ["Atlas Cloud", "Summit Logic", "Modern Metrics", "Prime Workflow"],
    },
    "finance": {
        "job_title": ["Financial Analyst", "Risk Manager", "Account Manager", "Chief Financial Officer"],
        "company_name": ["North Capital", "Summit Finance", "Blue Ledger", "Apex Banking"],
    },
}

SEMANTIC_REQUIREMENTS: Dict[str, Set[str]] = {
    "first_name": {"first_name"},
    "last_name": {"last_name"},
    "person_name": {"name"},
    "email": {"email"},
    "username": {"username"},
    "company_name": {"company", "company_name", "organization"},
    "job_title": {"job_title", "role", "title", "position"},
    "country": {"country"},
    "state": {"state", "province", "region"},
    "city": {"city"},
    "product_name": {"name", "product_name", "title"},
    "product_description": {"description", "summary"},
}

SEMANTIC_TO_ASSET = {
    "person_name": ["first_name", "last_name"],
    "email": ["first_name", "last_name"],
    "username": ["first_name", "last_name"],
    "first_name": ["first_name"],
    "last_name": ["last_name"],
    "company_name": ["company_name"],
    "job_title": ["job_title"],
    "country": ["country"],
    "state": ["state"],
    "city": ["city"],
    "product_name": ["product_name"],
    "product_description": ["product_description"],
}


class SemanticVocabularyGenerator:
    """Compile a domain capsule from schema hints and asset-backed vocabularies."""

    def __init__(self, asset_store: Optional[AssetStore] = None):
        self.asset_store = asset_store or AssetStore()

    def build_capsule(self, schema_config: Any) -> DomainCapsule:
        realism = getattr(schema_config, "realism", None)
        table_names = [table.name for table in schema_config.tables]
        domain = (
            getattr(realism, "domain_hint", None)
            or detect_reference_domain(table_names)
            or "generic"
        )
        locale = getattr(realism, "locale", None) or "global"
        era = getattr(realism, "era", None)

        capsule = DomainCapsule(
            domain=domain,
            locale=locale,
            era=era,
            metadata={"tables": table_names},
        )

        required_assets = self._required_assets(schema_config)
        for asset_name in sorted(required_assets):
            assets = self.asset_store.load_vocabulary(asset_name, domain=domain, locale=locale, era=era)
            if assets:
                for asset in assets:
                    capsule.record_asset(asset)
                continue

            fallback_values = self._fallback_values(asset_name, domain)
            if fallback_values:
                fallback_asset = VocabularyAsset(
                    name=asset_name,
                    values=fallback_values,
                    provenance=AssetProvenance(
                        source_type="built_in",
                        source_name="misata-defaults",
                        license_name="internal",
                        metadata={"domain": domain},
                    ),
                    domain=domain,
                    locale=locale,
                    era=era,
                    tags=["fallback"],
                )
                capsule.record_asset(fallback_asset)

        return capsule

    def _required_assets(self, schema_config: Any) -> Set[str]:
        assets: Set[str] = set()
        for table in schema_config.tables:
            table_name = table.name.lower()
            for column in schema_config.get_columns(table.name):
                semantic = self._infer_semantic(column.name.lower(), table_name)
                assets.update(SEMANTIC_TO_ASSET.get(semantic, []))
        return assets

    def _infer_semantic(self, column_name: str, table_name: str) -> str:
        if column_name == "first_name":
            return "first_name"
        if column_name == "last_name":
            return "last_name"
        if "email" in column_name:
            return "email"
        if "username" in column_name:
            return "username"
        if "company" in column_name or "organization" in column_name:
            return "company_name"
        if "job" in column_name or "role" in column_name or "title" in column_name or "position" in column_name:
            return "job_title"
        if "country" in column_name:
            return "country"
        if "state" in column_name or "province" in column_name or "region" in column_name:
            return "state"
        if "city" in column_name:
            return "city"
        if ("product" in table_name or "item" in table_name) and column_name in {"name", "product_name", "title"}:
            return "product_name"
        if ("product" in table_name or "item" in table_name) and ("description" in column_name or "summary" in column_name):
            return "product_description"
        if column_name == "name":
            return "person_name"
        return "generic"

    def _fallback_values(self, asset_name: str, domain: str) -> List[str]:
        if domain in DOMAIN_SPECIFIC_DEFAULTS and asset_name in DOMAIN_SPECIFIC_DEFAULTS[domain]:
            return list(DOMAIN_SPECIFIC_DEFAULTS[domain][asset_name])
        return list(DEFAULT_VOCABULARIES.get(asset_name, []))
