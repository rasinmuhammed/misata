"""MkDocs SEO hook: cross-domain canonicalization to Misata Studio.

Several guide/reference pages exist on BOTH this docs site
(rasinmuhammed.github.io/misata) and the product site
(misata.studio/docs/<slug>). Duplicate content across two domains splits link
equity and suppresses both. misata.studio is the primary brand domain, so for
every page whose basename matches a Studio doc slug we point the canonical URL
at the Studio copy. Google then consolidates ranking signals onto one URL.

Pages with no Studio equivalent keep their own github.io canonical untouched.
"""
from __future__ import annotations

# Doc slugs that also live at https://misata.studio/docs/<slug>. Keep in sync
# with apps/web/content/docs/*.md in the misata-studio repo.
_STUDIO_DOC_SLUGS = {
    "cli",
    "constraints",
    "database-seeding-python",
    "domains",
    "export",
    "faker-vs-sdv-vs-misata",
    "localisation",
    "multi-table-synthetic-data",
    "python-synthetic-data-generator",
    "quickstart",
    "synthetic-data-for-bi-demos",
    "timeseries",
    "validate",
}

_STUDIO_DOCS_BASE = "https://misata.studio/docs"


def _basename(src_uri: str) -> str:
    """`guides/faker-vs-sdv-vs-misata.md` -> `faker-vs-sdv-vs-misata`."""
    leaf = src_uri.rsplit("/", 1)[-1]
    return leaf[:-3] if leaf.endswith(".md") else leaf


def on_page_context(context, page, config, nav):
    """Override canonical_url before the template renders it."""
    slug = _basename(page.file.src_uri)
    if slug in _STUDIO_DOC_SLUGS:
        page.canonical_url = f"{_STUDIO_DOCS_BASE}/{slug}"
    return context
