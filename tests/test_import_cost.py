"""``import misata`` stays cheap, and the lazily loaded public API stays whole."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import types
from pathlib import Path

import pytest

import misata

ROOT = Path(__file__).resolve().parents[1]

#: Modules that only the code paths needing them may load. Asserting on what
#: is loaded rather than on elapsed time keeps the check stable on noisy CI.
HEAVY = ("scipy", "networkx", "jinja2", "duckdb", "misata.llm_parser", "misata.solve")


def _run(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          check=True, cwd=ROOT)
    return done.stdout


def test_import_loads_no_heavy_module():
    loaded = set(json.loads(_run("import json, sys, misata; print(json.dumps(sorted(sys.modules)))")))
    assert not loaded & set(HEAVY)


def test_import_resolves_this_checkout():
    assert Path(_run("import misata; print(misata.__file__)").strip()) == ROOT / "misata" / "__init__.py"


@pytest.mark.parametrize("name", misata.__all__)
def test_every_public_name_resolves(name):
    assert getattr(misata, name) is not None
    namespace: dict = {}
    exec(f"from misata import {name}", namespace)
    assert namespace[name] is getattr(misata, name)


def test_dir_lists_every_public_name():
    assert set(misata.__all__) <= set(dir(misata))


def test_unknown_name_is_an_attribute_error():
    assert not hasattr(misata, "no_such_name")
    with pytest.raises(AttributeError, match="no_such_name"):
        misata.no_such_name  # noqa: B018


def test_submodules_resolve_as_attributes():
    assert isinstance(misata.introspect, types.ModuleType)
    assert misata.spark.__name__ == "misata.spark"


def test_exported_functions_outlive_their_submodule_import():
    # ``solve``, ``explain`` and ``fingerprint`` live in submodules of the same
    # name; importing the submodule first must not rebind the package name.
    out = _run(
        "import types, misata.solve, misata.explain, misata.fingerprint\n"
        "import misata\n"
        "print(all(callable(misata.__dict__[n]) and not isinstance(misata.__dict__[n], types.ModuleType)"
        " for n in ('solve', 'explain', 'fingerprint')))"
    )
    assert out.strip() == "True"


def _type_checking_imports() -> dict:
    """Name -> (module, attribute) for every import under ``if TYPE_CHECKING:``."""
    tree = ast.parse((ROOT / "misata" / "__init__.py").read_text(encoding="utf-8"))
    block = next(node for node in tree.body
                 if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                 and node.test.id == "TYPE_CHECKING")
    imports = {}
    for node in block.body:
        assert isinstance(node, ast.ImportFrom)
        for alias in node.names:
            imports[alias.asname or alias.name] = (node.module, alias.name)
    return imports


def test_type_checking_block_mirrors_lazy_table():
    imports = _type_checking_imports()
    submodules = {name for name, (module, _) in imports.items() if module == "misata"}
    assert {k: v for k, v in imports.items() if k not in submodules} == misata._LAZY
    for name in submodules:
        assert isinstance(getattr(misata, name), types.ModuleType)
