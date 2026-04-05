"""Local asset store and Kaggle-ready ingestion interfaces."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from typing import Any, Dict, Iterable, List, Optional

from misata.domain_capsule import AssetProvenance, VocabularyAsset


DEFAULT_ALLOWED_LICENSES = {
    "CC0-1.0",
    "PDDL",
    "US-Government-Works",
    "CDLA-Permissive-1.0",
    "CC-BY-4.0",
    "CC-BY-3.0",
}

DEFAULT_BLOCKED_LICENSES = {
    "CC-BY-NC-4.0",
    "CC-BY-NC-SA-4.0",
    "CC-BY-NC-ND-4.0",
    "CC-BY-ND-4.0",
    "copyright-authors",
    "other",
    "unknown",
}


@dataclass
class KaggleDatasetDescriptor:
    """Metadata needed to ingest a Kaggle dataset safely."""

    dataset_ref: str
    title: str
    license_name: str
    attribution: Optional[str] = None
    domain: Optional[str] = None
    locale: Optional[str] = None
    era: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class KaggleIngestionResult:
    """Summary of an ingestion run."""

    accepted: bool
    assets_written: int = 0
    license_name: Optional[str] = None
    reason: Optional[str] = None


class LicensePolicy:
    """Simple allow/block policy for dataset licenses."""

    def __init__(
        self,
        allowed: Optional[Iterable[str]] = None,
        blocked: Optional[Iterable[str]] = None,
    ):
        self.allowed = {license_name for license_name in (allowed or DEFAULT_ALLOWED_LICENSES)}
        self.blocked = {license_name for license_name in (blocked or DEFAULT_BLOCKED_LICENSES)}

    def is_allowed(self, license_name: str) -> bool:
        """Return whether a license is allowed for ingestion."""
        normalized = (license_name or "").strip()
        if normalized in self.blocked:
            return False
        return normalized in self.allowed

    def explain(self, license_name: str) -> str:
        """Human-readable policy result."""
        normalized = (license_name or "").strip()
        if normalized in self.blocked:
            return f"License '{normalized}' is blocked by policy"
        if normalized not in self.allowed:
            return f"License '{normalized}' is not in the allowlist"
        return f"License '{normalized}' is allowed"


class AssetStore:
    """Versioned local store for reusable vocabulary assets."""

    def __init__(self, root_dir: Optional[str] = None):
        default_root = Path.home() / ".misata" / "assets"
        preferred_root = Path(root_dir).expanduser() if root_dir else default_root
        self.root = self._ensure_writable_root(preferred_root)

    def save_vocabulary_asset(self, asset: VocabularyAsset) -> Path:
        """Persist one vocabulary asset as JSON."""
        directory = self._asset_dir(asset.domain, asset.locale, asset.era)
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{asset.name}.json"
        path = directory / filename
        payload = {
            "name": asset.name,
            "values": asset.values,
            "domain": asset.domain,
            "locale": asset.locale,
            "era": asset.era,
            "tags": asset.tags,
            "provenance": asdict(asset.provenance),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def load_vocabulary(
        self,
        name: str,
        *,
        domain: Optional[str] = None,
        locale: Optional[str] = None,
        era: Optional[str] = None,
    ) -> List[VocabularyAsset]:
        """Load matching vocabulary assets with fallback from specific to generic."""
        candidates = [
            self._asset_dir(domain, locale, era) / f"{name}.json",
            self._asset_dir(domain, locale, None) / f"{name}.json" if era else None,
            self._asset_dir(domain, None, None) / f"{name}.json" if domain else None,
            self._asset_dir("generic", locale, era) / f"{name}.json" if locale or era else None,
            self._asset_dir("generic", "global", None) / f"{name}.json",
        ]
        assets = []
        seen = set()
        for candidate in candidates:
            if candidate is None or candidate in seen or not candidate.exists():
                continue
            seen.add(candidate)
            payload = json.loads(candidate.read_text(encoding="utf-8"))
            provenance = AssetProvenance(**payload.get("provenance", {}))
            assets.append(
                VocabularyAsset(
                    name=payload["name"],
                    values=list(payload.get("values", [])),
                    provenance=provenance,
                    domain=payload.get("domain"),
                    locale=payload.get("locale"),
                    era=payload.get("era"),
                    tags=list(payload.get("tags", [])),
                )
            )
        return assets

    def _asset_dir(
        self,
        domain: Optional[str],
        locale: Optional[str],
        era: Optional[str],
    ) -> Path:
        resolved_domain = (domain or "generic").replace(" ", "_").lower()
        resolved_locale = (locale or "global").replace(" ", "_")
        base = self.root / resolved_domain / resolved_locale
        if era:
            return base / era.replace(" ", "_").lower()
        return base

    def _ensure_writable_root(self, preferred_root: Path) -> Path:
        try:
            preferred_root.mkdir(parents=True, exist_ok=True)
            return preferred_root
        except PermissionError:
            fallback_root = Path(tempfile.gettempdir()) / ".misata" / "assets"
            fallback_root.mkdir(parents=True, exist_ok=True)
            return fallback_root


class KaggleAssetIngestor:
    """Convert Kaggle-exported files into local vocabulary assets."""

    def __init__(
        self,
        asset_store: AssetStore,
        license_policy: Optional[LicensePolicy] = None,
    ):
        self.asset_store = asset_store
        self.license_policy = license_policy or LicensePolicy()

    def ingest_csv(
        self,
        descriptor: KaggleDatasetDescriptor,
        csv_path: str,
        column_to_asset: Dict[str, str],
        *,
        limit: Optional[int] = None,
        dedupe: bool = True,
    ) -> KaggleIngestionResult:
        """Ingest selected CSV columns into versioned vocabulary assets."""
        if not self.license_policy.is_allowed(descriptor.license_name):
            return KaggleIngestionResult(
                accepted=False,
                license_name=descriptor.license_name,
                reason=self.license_policy.explain(descriptor.license_name),
            )

        rows = self._read_csv_rows(csv_path, limit=limit)
        assets_written = 0
        for column_name, asset_name in column_to_asset.items():
            values = [row.get(column_name, "").strip() for row in rows if row.get(column_name)]
            if dedupe:
                values = list(dict.fromkeys(values))
            if not values:
                continue

            provenance = AssetProvenance(
                source_type="kaggle",
                source_name=descriptor.dataset_ref,
                license_name=descriptor.license_name,
                attribution=descriptor.attribution,
                collected_at=datetime.now(timezone.utc).isoformat(),
                metadata={"title": descriptor.title, **descriptor.metadata},
            )
            asset = VocabularyAsset(
                name=asset_name,
                values=values,
                provenance=provenance,
                domain=descriptor.domain,
                locale=descriptor.locale,
                era=descriptor.era,
                tags=list(descriptor.tags),
            )
            self.asset_store.save_vocabulary_asset(asset)
            assets_written += 1

        return KaggleIngestionResult(
            accepted=True,
            assets_written=assets_written,
            license_name=descriptor.license_name,
        )

    def _read_csv_rows(self, csv_path: str, *, limit: Optional[int]) -> List[Dict[str, str]]:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            rows: List[Dict[str, str]] = []
            for index, row in enumerate(reader):
                rows.append({key: (value or "") for key, value in row.items()})
                if limit is not None and index + 1 >= limit:
                    break
        return rows
