"""Write PYPI.md, the package's long description, from README.md.

    python tools/readme_pypi.py           # rewrite PYPI.md
    python tools/readme_pypi.py --check   # exit 1 when PYPI.md is stale

PyPI renders neither mermaid nor links relative to the repository, and it
drops <picture> sources. The PyPI page is the README with its diagrams left
out, each chart as its light image, and every relative link pointed at the
file on GitHub. The `mcp-name` comment is kept: the MCP registry reads it from
the PyPI description.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "README.md"
TARGET = ROOT / "PYPI.md"
REPO = "https://github.com/rasinmuhammed/misata"

MERMAID = re.compile(r"\n```mermaid\n.*?\n```\n", re.S)
PICTURE = re.compile(r"<picture>\s*<source[^>]*>\s*(<img[^>]*>)\s*</picture>", re.S)
STRANGER = re.compile(r"<!-- stranger:[^>]*-->\n")
MD_LINK = re.compile(r"(\]\()(?!https?://|#|mailto:)([^)\s]+)(\))")
HTML_LINK = re.compile(r"""(href=")(?!https?://|#|mailto:)([^"]+)(")""")


def _absolute(path: str) -> str:
    kind = "tree" if path.endswith("/") or (ROOT / path).is_dir() else "blob"
    return f"{REPO}/{kind}/main/{path.removeprefix('./')}"


def render(readme: str) -> str:
    text = MERMAID.sub("\n", readme)
    text = PICTURE.sub(r"\1", text)
    text = STRANGER.sub("", text)
    text = MD_LINK.sub(lambda m: m[1] + _absolute(m[2]) + m[3], text)
    text = HTML_LINK.sub(lambda m: m[1] + _absolute(m[2]) + m[3], text)
    return re.sub(r"\n{3,}", "\n\n", text)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail when PYPI.md is stale")
    args = parser.parse_args(argv)
    rendered = render(SOURCE.read_text(encoding="utf-8"))
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != rendered:
            print("PYPI.md is stale: run python tools/readme_pypi.py")
            return 1
        return 0
    TARGET.write_text(rendered, encoding="utf-8")
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
