"""Anchored RNG streams: schema edits produce minimal data diffs.

Legacy generation draws every value from one sequential stream, so any
schema edit (a new column, a tweaked range) shifts the stream and reshuffles
everything generated after it. The whole dataset becomes the diff.

Anchored mode derives an independent stream per generation site from the
schema seed and the site's stable name:

    rng = derive_rng(seed, "column", "orders", "revenue", 0)

Because a site's stream depends only on its own name, adding a column leaves
every other column byte-identical, adding a table leaves every other table
byte-identical, and editing one column re-rolls only that column plus its
true dependents (formulas reading it, children sampling its keys, identities
rewriting it). Edits flow DOWN the dependency graph, never sideways.

Enable with ``generation_mode: "anchored"`` on the schema. Bytes differ from
legacy mode for the same seed, which is why it is opt-in; the reproducibility
policy (same version + same seed + same mode = same bytes) holds in both.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

import numpy as np


def derive_seed(seed: Optional[int], *parts: Any) -> int:
    """Stable 64-bit seed from the schema seed and a site's name parts.

    Uses blake2b over a canonical encoding, so the value is identical across
    processes, platforms, and Python versions (unlike ``hash()``).
    """
    h = hashlib.blake2b(digest_size=8)
    h.update(str(int(seed if seed is not None else 42)).encode())
    for part in parts:
        h.update(b"\x1f")  # unit separator: ("ab","c") != ("a","bc")
        h.update(str(part).encode())
    return int.from_bytes(h.digest(), "big")


def derive_rng(seed: Optional[int], *parts: Any) -> np.random.Generator:
    """An independent generator anchored to (seed, *parts)."""
    return np.random.default_rng(derive_seed(seed, *parts))


@contextmanager
def anchored_rng(holders: Sequence[Any], seed: Optional[int],
                 *parts: Any) -> Iterator[np.random.Generator]:
    """Swap ``holder.rng`` on every holder to one anchored stream, restore after.

    Generation is single-threaded, so a scoped swap is safe and reaches every
    helper that reads ``self.rng`` without threading a generator through
    dozens of call sites.
    """
    rng = derive_rng(seed, *parts)
    saved = [(h, h.rng) for h in holders if hasattr(h, "rng")]
    for h, _ in saved:
        h.rng = rng
    try:
        yield rng
    finally:
        for h, old in saved:
            h.rng = old
