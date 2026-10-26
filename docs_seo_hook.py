"""MkDocs SEO hook: canonical URLs on misata.studio.

Every page of this docs site is also served at https://www.misata.studio/docs
under the same path (``guides/attest.md`` at ``/docs/guides/attest``). Two
copies of a page on two domains split ranking signals, so each page here names
the misata.studio copy as its canonical URL and search engines consolidate
onto one address.
"""
from __future__ import annotations

_STUDIO_DOCS_BASE = "https://www.misata.studio/docs"

# Older top-level copies of pages whose maintained version lives under guides/.
# misata.studio redirects these paths, so the canonical names the destination.
_MOVED = {
    "database-seeding-python": "guides/database-seeding-python",
    "faker-vs-sdv-vs-misata": "guides/faker-vs-sdv-vs-misata",
    "multi-table-synthetic-data": "guides/multi-table-synthetic-data",
    "synthetic-data-for-bi-demos": "guides/synthetic-data-for-bi-demos",
}


def studio_path(src_uri: str) -> str:
    """`guides/attest.md` -> `guides/attest`; `usecases/index.md` -> `usecases`; `index.md` -> ``."""
    path = src_uri[:-3] if src_uri.endswith(".md") else src_uri
    if path == "index":
        return ""
    if path.endswith("/index"):
        path = path[: -len("/index")]
    return _MOVED.get(path, path)


def on_page_context(context, page, config, nav):
    """Override canonical_url before the template renders it."""
    path = studio_path(page.file.src_uri)
    page.canonical_url = f"{_STUDIO_DOCS_BASE}/{path}" if path else _STUDIO_DOCS_BASE
    return context
