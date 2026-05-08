"""Misata MCP server — expose synthetic data generation to AI agents.

Run via the ``misata-mcp`` console script after installing with::

    pip install "misata[mcp]"

Then add to your Claude Desktop / Cursor / Windsurf config::

    {
      "mcpServers": {
        "misata": { "command": "misata-mcp" }
      }
    }
"""

from misata.mcp.server import main, mcp

__all__ = ["main", "mcp"]
