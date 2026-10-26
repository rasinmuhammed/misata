"""The README's links resolve, its charts exist, and PYPI.md is rendered from it."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = (ROOT / "README.md").read_text(encoding="utf-8")


def test_pypi_description_is_rendered_from_the_readme():
    sys.path.insert(0, str(ROOT / "tools"))
    try:
        import readme_pypi
    finally:
        sys.path.pop(0)
    assert (ROOT / "PYPI.md").read_text(encoding="utf-8") == readme_pypi.render(README), \
        "PYPI.md is stale: run python tools/readme_pypi.py"


def test_relative_links_resolve():
    links = re.findall(r"\]\((?!https?://|#)([^)\s]+)\)", README)
    links += re.findall(r'href="(?!https?://|#)([^"]+)"', README)
    missing = [link for link in links if not (ROOT / link).exists()]
    assert links and not missing, missing


def test_charts_are_in_the_repository():
    charts = re.findall(r"raw\.githubusercontent\.com/rasinmuhammed/misata/main/([^\"]+\.svg)", README)
    assert len(charts) == 10
    assert all((ROOT / chart).is_file() for chart in charts)


def test_no_em_dashes():
    assert "—" not in README
