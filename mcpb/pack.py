"""Build `misata.mcpb`, the file the desktop extension form takes.

An `.mcpb` is a zip with `manifest.json` at its root. That is the whole format,
so this builds one directly rather than shelling out to `npx @anthropic-ai/mcpb`:
one fewer toolchain to have installed, and nothing downloaded at build time.

It validates before it packs, and refuses rather than producing a bundle that
would be rejected on upload:

  - the manifest parses and carries every field the directory requires
  - its version matches the installed `misata`, so the listing cannot describe
    a release that does not exist
  - its tool list matches the tools the server actually registers
  - an icon is present

Run from the repository root:

    python mcpb/pack.py
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# The directory rejects a submission missing any of these, and the rejection
# arrives days later, so check now.
REQUIRED = [
    "manifest_version", "name", "display_name", "version", "description",
    "author", "server", "tools", "privacy_policies", "license",
    "documentation",
]


def registered_tools() -> set[str] | None:
    """What the server actually exposes, or None if `mcp` is not installed.

    A manifest that lists a tool the server dropped is a listing that lies, and
    nobody notices until a user asks for it by name.
    """
    try:
        sys.path.insert(0, str(ROOT))
        from misata.mcp.server import mcp
    except ImportError:
        return None

    import asyncio
    return {t.name for t in asyncio.run(mcp.list_tools())}


def main() -> int:
    manifest_path = HERE / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    problems: list[str] = []

    missing = [k for k in REQUIRED if k not in manifest]
    if missing:
        problems.append(f"manifest is missing required field(s): {missing}")

    if not manifest.get("privacy_policies"):
        problems.append("privacy_policies is empty; a missing privacy policy is "
                        "an immediate rejection")

    try:
        sys.path.insert(0, str(ROOT))
        import misata
        if manifest["version"] != misata.__version__:
            problems.append(
                f"manifest version {manifest['version']} != installed misata "
                f"{misata.__version__}; the listing would name a release that "
                "does not exist")
    except ImportError:
        problems.append("misata is not importable, so the version cannot be checked")

    declared = {t["name"] for t in manifest.get("tools", [])}
    actual = registered_tools()
    if actual is None:
        print('  note: `mcp` not installed, so the tool list was not checked '
              '(pip install "misata[mcp]")')
    elif declared != actual:
        if declared - actual:
            problems.append(f"manifest lists tools the server does not have: "
                            f"{sorted(declared - actual)}")
        if actual - declared:
            problems.append(f"server has tools the manifest does not list: "
                            f"{sorted(actual - declared)}")

    icon = HERE / "icon.png"
    if not icon.exists():
        problems.append(
            "mcpb/icon.png is missing. The directory needs a square PNG with a "
            "transparent background; without it the submission has no artwork.")

    if problems:
        print("Refusing to pack:")
        for p in problems:
            print(f"  - {p}")
        return 1

    out = HERE / "misata.mcpb"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(manifest_path, "manifest.json")
        z.write(HERE / "README.md", "README.md")
        z.write(icon, "icon.png")

    print(f"  {out.relative_to(ROOT)}  "
          f"{out.stat().st_size / 1024:.1f} KB  "
          f"v{manifest['version']}, {len(declared)} tools")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
