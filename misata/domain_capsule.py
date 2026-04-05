"""Typed domain capsule for asset-backed realism generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AssetProvenance:
    """Metadata describing where a vocabulary asset came from."""

    source_type: str
    source_name: str
    license_name: str
    attribution: Optional[str] = None
    collected_at: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VocabularyAsset:
    """A named vocabulary with provenance and optional scope."""

    name: str
    values: List[str]
    provenance: AssetProvenance
    domain: Optional[str] = None
    locale: Optional[str] = None
    era: Optional[str] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class DomainCapsule:
    """Resolved domain context used by realism-aware generators."""

    domain: str = "generic"
    locale: str = "global"
    era: Optional[str] = None
    vocabularies: Dict[str, List[str]] = field(default_factory=dict)
    provenance: Dict[str, List[AssetProvenance]] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_values(self, name: str, fallback: Optional[List[str]] = None) -> List[str]:
        """Return a vocabulary list, falling back when absent or empty."""
        values = self.vocabularies.get(name, [])
        if values:
            return values
        return list(fallback or [])

    def record_asset(self, asset: VocabularyAsset) -> None:
        """Add a vocabulary asset into the capsule."""
        if asset.values:
            existing = self.vocabularies.setdefault(asset.name, [])
            seen = set(existing)
            for value in asset.values:
                if value not in seen:
                    existing.append(value)
                    seen.add(value)
        self.provenance.setdefault(asset.name, []).append(asset.provenance)
