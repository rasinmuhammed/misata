"""
Misata Studio - Visual Schema Designer & Reverse Graph Editor

The GUI for reverse-engineering schemas from sample data and
designing custom distributions visually.

Usage:
    pip install misata[studio]
    misata studio
    
    # Or from Python:
    from misata.studio import launch
    launch()
"""

from typing import Optional


def launch(
    port: int = 8501,
    host: str = "localhost",
    open_browser: bool = True,
) -> None:
    """Launch Misata Studio GUI.
    
    Args:
        port: Port to run on (default 8501)
        host: Host to bind to (default localhost)
        open_browser: Open browser automatically
    """
    try:
        import streamlit.web.cli as stcli
        import sys
        import os
        
        # Get the path to app.py
        app_path = os.path.join(os.path.dirname(__file__), "app.py")
        
        sys.argv = [
            "streamlit", "run", app_path,
            f"--server.port={port}",
            f"--server.address={host}",
            "--server.headless=true" if not open_browser else "",
        ]
        sys.argv = [arg for arg in sys.argv if arg]  # Remove empty strings
        
        stcli.main()
    except ImportError:
        raise ImportError(
            "Misata Studio requires streamlit. Install with:\n"
            "  pip install misata[studio]"
        )


__all__ = ["launch"]
