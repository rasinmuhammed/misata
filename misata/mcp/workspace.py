"""The part of the filesystem MCP tools may read from and write to.

Every path an agent passes to a tool (an output directory, a dataset folder, a
sandbox file) is resolved, symlinks included, and must land inside one of the
allowed roots. An agent's arguments can be steered by text it has read, so a
tool that writes files or opens databases accepts a path only where the user
has agreed to let it work.

Allowed roots, in order:

* every directory listed in ``MISATA_MCP_ROOTS`` (separated by ``os.pathsep``).
  When the variable is set, it is the complete list;
* otherwise, the server's working directory, unless that is the filesystem
  root (some desktop clients start servers there), plus the system temporary
  directory.

Relative paths resolve against the working directory when it is an allowed
root, and against a ``misata`` folder in the temporary directory otherwise.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Tuple, Union

__all__ = ["ROOTS_ENV_VAR", "PathNotAllowedError", "allowed_roots", "confine", "workspace"]

ROOTS_ENV_VAR = "MISATA_MCP_ROOTS"


class PathNotAllowedError(PermissionError):
    """A tool argument named a path outside every allowed root."""


def allowed_roots() -> Tuple[Path, ...]:
    """The directories tools may touch, resolved, without duplicates."""
    configured = os.environ.get(ROOTS_ENV_VAR, "")
    if configured.strip():
        roots = [Path(p).expanduser().resolve() for p in configured.split(os.pathsep) if p.strip()]
    else:
        roots = [Path(tempfile.gettempdir()).resolve()]
        cwd = Path.cwd().resolve()
        if cwd != Path(cwd.anchor):
            roots.insert(0, cwd)
    return tuple(dict.fromkeys(roots))


def workspace() -> Path:
    """Directory that relative tool paths resolve against."""
    cwd = Path.cwd().resolve()
    if any(cwd == root or cwd.is_relative_to(root) for root in allowed_roots()):
        return cwd
    return Path(tempfile.gettempdir()).resolve() / "misata"


def confine(path: Union[str, Path]) -> Path:
    """Resolve ``path`` and return it if it lies inside an allowed root.

    Raises:
        PathNotAllowedError: the resolved path is outside every allowed root.
    """
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = workspace() / candidate
    resolved = candidate.resolve()
    roots = allowed_roots()
    if any(resolved == root or resolved.is_relative_to(root) for root in roots):
        return resolved
    listed = ", ".join(str(r) for r in roots)
    raise PathNotAllowedError(
        f"{resolved} is outside the directories this server may use ({listed}). "
        f"Use a path inside one of them, or have the user add a directory to "
        f"{ROOTS_ENV_VAR} in the server's configuration."
    )
