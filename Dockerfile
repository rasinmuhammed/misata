# Container image for the Misata MCP server.
#
# Directory builders (Glama and anything else that builds from the repo rather
# than from PyPI) start a container and spawn `misata-mcp`. Without this file
# there was nothing to install the package, so the entry point did not exist
# and the container died with `spawn misata-mcp ENOENT` before it could answer
# a ping.
#
# The server speaks MCP over stdio, so nothing here may write to stdout: the
# transport is the stdout stream. PYTHONUNBUFFERED keeps stderr diagnostics
# prompt without touching it.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Metadata first so a source-only change does not re-resolve dependencies.
COPY pyproject.toml README.md ./
COPY misata ./misata

# `[mcp]` pulls the FastMCP runtime; `[formulas]` provides simpleeval, without
# which a column declared as `qty * unit_price` silently has no evaluator.
RUN pip install --no-cache-dir ".[mcp,formulas]"

# Not root, because this image runs code that reads schemas it was handed.
RUN useradd --create-home --uid 10001 misata
USER misata

# Fail the build here rather than at first spawn: if the console script is
# missing, that is the exact failure this file exists to prevent. `command -v`
# resolves the script without executing it, which matters because main() takes
# no arguments and goes straight into the stdio loop, so actually running it
# here would block the build forever.
RUN command -v misata-mcp && python -c "import misata.mcp.server"

ENTRYPOINT ["misata-mcp"]
