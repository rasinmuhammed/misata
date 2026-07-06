"""Vocabulary validator: the property gate every vocabulary source must pass.

No source of values is infallible — an LLM invents "John Doe", a mined CSV
carries free-text sentences, even Wikidata has vandalized labels. What CAN be
guaranteed mechanically is the absence of known fake-data classes. This module
is that guarantee: every capsule ingestion path (LLM, Wikidata, CSV mining,
schema vocabulary blocks) runs candidates through ``validate_vocabulary`` so a
label list never contains placeholders, sentences, duplicates, or junk,
regardless of where it came from.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Tuple

# Placeholder identities and filler tokens that mark a value as fake on sight.
# Compared lowercase against the full trimmed value.
_PLACEHOLDER_VALUES = {
    "john doe", "jane doe", "john smith", "jane smith", "bob johnson",
    "alice williams", "mike davis", "joe bloggs", "max mustermann",
    "test", "test user", "test name", "sample", "example", "demo",
    "placeholder", "tbd", "todo", "n/a", "na", "none", "null", "unknown",
    "foo", "bar", "baz", "qux", "lorem ipsum", "asdf", "xyz", "abc",
    "value", "item", "name", "label", "string", "text", "data",
}

# "Value A", "Item 1", "Type 2", "Option B" style enumerated filler.
_ENUMERATED_FILLER_RE = re.compile(
    r"^(value|item|type|option|label|category|thing|entry|record|sample|test)"
    r"\s*[-_ ]?\s*([a-z]|\d{1,3})$",
    re.IGNORECASE,
)

# Wikidata returns the QID itself as the label for unlabeled entities.
_QID_RE = re.compile(r"^Q\d+$")

# Sentence heuristics: labels are noun phrases, not prose.
_MAX_LABEL_WORDS = 6
_MAX_LABEL_CHARS = 80


@dataclass
class ValidationResult:
    """Accepted values plus the rejects and why, for review/reporting."""

    accepted: List[str] = field(default_factory=list)
    rejected: List[Tuple[str, str]] = field(default_factory=list)  # (value, reason)

    @property
    def ok(self) -> bool:
        return len(self.accepted) >= 2

    def summary(self) -> str:
        return (
            f"{len(self.accepted)} accepted, {len(self.rejected)} rejected"
            + (f" ({', '.join(sorted({r for _, r in self.rejected}))})" if self.rejected else "")
        )


def _reject_reason(value: str) -> Optional[str]:
    """Reason this value must not enter a vocabulary, or None if it's fine."""
    v = value.strip()
    if not v:
        return "empty"
    low = v.lower()
    if low in _PLACEHOLDER_VALUES:
        return "placeholder"
    if _ENUMERATED_FILLER_RE.match(v):
        return "enumerated-filler"
    if _QID_RE.match(v):
        return "unlabeled-entity"
    if len(v) > _MAX_LABEL_CHARS:
        return "too-long"
    words = v.split()
    if len(words) > _MAX_LABEL_WORDS:
        return "sentence-not-label"
    # Prose tell: ends with sentence punctuation and reads like a clause.
    if len(words) >= 4 and v.endswith((".", "!", "?")):
        return "sentence-not-label"
    # Values with no letters at all are ids, not labels.
    if not re.search(r"[A-Za-z]", v):
        return "no-letters"
    return None


def validate_vocabulary(values: Iterable[str]) -> ValidationResult:
    """Filter a candidate vocabulary down to values safe to generate from.

    Deduplicates case-insensitively (first occurrence wins) and rejects
    placeholders, enumerated filler, prose, unlabeled entities, and junk.
    Order is preserved so curated rankings survive.
    """
    result = ValidationResult()
    seen: set = set()
    for raw in values:
        v = str(raw).strip()
        reason = _reject_reason(v)
        if reason is not None:
            result.rejected.append((v, reason))
            continue
        key = v.lower()
        if key in seen:
            result.rejected.append((v, "duplicate"))
            continue
        seen.add(key)
        result.accepted.append(v)
    return result
