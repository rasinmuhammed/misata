"""Integration tests: every script in examples/ must execute cleanly.

Examples are user-facing artifacts. If they break — even silently — the
library's first impression is broken. This file runs every Python example
as a subprocess and asserts a zero exit code.

Heavy examples (notebooks, anything > a few seconds) are skipped here;
the goal is fast smoke coverage that catches API drift, removed exports,
and broken stories.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES_DIR = REPO_ROOT / "examples"


def _example_scripts() -> list[Path]:
    if not EXAMPLES_DIR.exists():
        return []
    return sorted(EXAMPLES_DIR.glob("*.py"))


@pytest.mark.parametrize(
    "script",
    _example_scripts(),
    ids=lambda p: p.name,
)
def test_example_runs_without_error(script, tmp_path):
    """Each example must execute cleanly with the current library API."""
    if not script.exists():
        pytest.skip(f"{script.name} missing")

    # Scripts that need live API keys / network (manual dev tools) — can't run
    # cleanly in a few seconds without credentials.
    if script.name in {"provider_bakeoff.py"}:
        pytest.skip(f"{script.name} requires live LLM credentials / network")

    # Run with the example's directory as cwd so any relative I/O lands in tmp_path.
    env = os.environ.copy()
    env["PYTHONWARNINGS"] = "ignore"
    env["MPLBACKEND"] = "Agg"  # never open a GUI

    result = subprocess.run(
        [sys.executable, str(script)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    assert result.returncode == 0, (
        f"Example {script.name} failed (exit {result.returncode}):\n"
        f"--- stdout ---\n{result.stdout[-2000:]}\n"
        f"--- stderr ---\n{result.stderr[-2000:]}"
    )
