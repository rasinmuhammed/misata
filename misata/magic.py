"""
IPython / Jupyter magic extension for Misata.

Load once per session::

    %load_ext misata.magic

Then generate datasets inline::

    %%misata rows=500
    social media app with followers, posts, and comments

    %%misata rows=1000 domain=fintech
    fintech app with transactions and wallets

Cell output: a dict of DataFrames is injected into the notebook namespace
under the variable name ``_misata`` (and each table as ``<table_name>_df``).
"""
from __future__ import annotations


def load_ipython_extension(ipython) -> None:  # type: ignore[type-arg]
    ipython.register_magic_function(_misata_cell, magic_kind="cell", magic_name="misata")


def _misata_cell(line: str, cell: str) -> None:  # type: ignore[type-arg]
    """%%misata [rows=N] [seed=N] — generate synthetic data from a story."""
    try:
        from IPython import get_ipython
        import pandas as pd
        from misata import generate
        from IPython.display import display, HTML
    except ImportError as exc:
        print(f"misata magic requires IPython and misata to be installed: {exc}")
        return

    ip = get_ipython()
    story = cell.strip()
    if not story:
        print("Usage: %%misata [rows=N] [seed=N]\\n<story>")
        return

    # Parse line args:  rows=500 seed=42
    kwargs: dict = {}
    for token in line.strip().split():
        if "=" in token:
            k, v = token.split("=", 1)
            try:
                kwargs[k.strip()] = int(v.strip())
            except ValueError:
                kwargs[k.strip()] = v.strip()

    rows = kwargs.pop("rows", 1_000)
    seed = kwargs.pop("seed", None)

    print(f"[misata] Generating: \"{story[:60]}{'...' if len(story)>60 else ''}\"  rows={rows}")

    tables = generate(story, rows=rows, seed=seed)

    # Inject into notebook namespace
    ip.user_ns["_misata"] = tables
    for name, df in tables.items():
        var = f"{name}_df"
        ip.user_ns[var] = df
        print(f"  → {var}  ({len(df):,} rows × {len(df.columns)} cols)")

    # Rich HTML summary table
    try:
        rows_html = "".join(
            f"<tr><td><code>{name}</code></td><td>{len(df):,}</td>"
            f"<td>{', '.join(df.columns[:6])}{'…' if len(df.columns)>6 else ''}</td></tr>"
            for name, df in tables.items()
        )
        html = (
            "<table style='font-size:13px;border-collapse:collapse'>"
            "<thead><tr><th>Table</th><th>Rows</th><th>Columns</th></tr></thead>"
            f"<tbody>{rows_html}</tbody></table>"
        )
        display(HTML(html))
    except Exception:
        pass
