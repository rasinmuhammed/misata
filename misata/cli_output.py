"""One output contract for every ``misata`` command.

Every command prints for people by default. With ``--json`` (or
``MISATA_JSON=1`` in the environment) it prints exactly one JSON document on
stdout instead, the envelope::

    {
      "envelope": 1,
      "ok": false,
      "command": "misata generate",
      "exit_code": 3,
      "code": "infeasible",
      "message": "1 declaration cannot be satisfied together: ...",
      "conflicts": [{"kind", "where", "declarations", "arithmetic", "remedy"}],
      "hint": "...",
      "data": null,
      "warnings": [{"category": "ConformanceWarning", "message": "..."}],
      "text": "what the command would have printed",
      "misata_version": "0.9.8"
    }

Exit codes are the same in both modes:

====  ===========  =====================================================
code  ``code``     meaning
====  ===========  =====================================================
0     ``ok``       the command did what was asked
1     ``failed``   it ran and a check failed, or it could not finish
2     ``usage``    bad arguments, or input it could not read
3     ``infeasible``  the declarations cannot all hold; nothing was written
====  ===========  =====================================================

A command adds structured results to the envelope with :func:`emit`. The
JSON Schema of the envelope ships in the package as
``misata/_schemas/cli-envelope.schema.json``.
"""

from __future__ import annotations

import contextvars
import io
import json
import os
import sys
import warnings
from contextlib import redirect_stdout
from dataclasses import dataclass, field
from typing import Any, Dict, List, NoReturn, Optional, Sequence

import click
import yaml

ENVELOPE_VERSION = 1
JSON_ENV_VAR = "MISATA_JSON"
_JSON_META = "misata.json"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_REFUSED = 3

_CODES = {EXIT_OK: "ok", EXIT_FAILED: "failed", EXIT_USAGE: "usage", EXIT_REFUSED: "infeasible"}

_REFUSED_HINT = ("Nothing was generated. Change the declarations each conflict names; "
                 "its remedy says how.")


@dataclass
class _Run:
    """What one command invocation has reported so far."""

    data: Dict[str, Any] = field(default_factory=dict)
    message: Optional[str] = None


_CURRENT: contextvars.ContextVar[Optional[_Run]] = contextvars.ContextVar(
    "misata_cli_run", default=None)


def json_mode() -> bool:
    """Whether the running command is producing a JSON envelope."""
    return _CURRENT.get() is not None


def emit(**data: Any) -> None:
    """Add structured results to the envelope; a no-op when printing for people."""
    run = _CURRENT.get()
    if run is not None:
        run.data.update(data)


def fail(message: str, exit_code: int = EXIT_FAILED) -> NoReturn:
    """Stop the command with ``exit_code``, saying why.

    People see the message in red on stderr; a JSON run carries it as the
    envelope's ``message``.
    """
    run = _CURRENT.get()
    if run is not None:
        run.message = message
    else:
        click.secho(message, fg="red", err=True)
    sys.exit(exit_code)


def _env_wants_json() -> bool:
    return os.environ.get(JSON_ENV_VAR, "").strip().lower() in {"1", "true", "yes", "on"}


def _jsonable(value: Any) -> Any:
    if hasattr(value, "item") and callable(value.item):
        try:
            return value.item()
        except (TypeError, ValueError):
            pass
    if isinstance(value, (set, frozenset, tuple)):
        return list(value)
    return str(value)


def _conflicts(exc: BaseException) -> List[Dict[str, Any]]:
    return [{"kind": c.kind, "where": c.where, "declarations": list(c.declarations),
             "arithmetic": c.arithmetic, "remedy": c.remedy}
            for c in getattr(exc, "conflicts", None) or []]


def _classify(exc: BaseException) -> int:
    """The exit code an exception escaping a command stands for."""
    from misata.exceptions import SchemaError
    from misata.feasibility import InfeasibleSchema

    if isinstance(exc, InfeasibleSchema):
        return EXIT_REFUSED
    if isinstance(exc, (click.UsageError, SchemaError, FileNotFoundError,
                        IsADirectoryError, json.JSONDecodeError, yaml.YAMLError)):
        return EXIT_USAGE
    return EXIT_FAILED


def _envelope(command: str, exit_code: int, *, data: Optional[Dict[str, Any]] = None,
              message: Optional[str] = None, error: Optional[BaseException] = None,
              caught: Sequence[warnings.WarningMessage] = (), text: str = "") -> Dict[str, Any]:
    from misata import __version__

    seen = set()
    warning_list = []
    for w in caught:
        key = (w.category.__name__, str(w.message))
        if key not in seen:
            seen.add(key)
            warning_list.append({"category": key[0], "message": key[1]})
    conflicts = _conflicts(error) if error is not None else []
    return {
        "envelope": ENVELOPE_VERSION,
        "ok": exit_code == EXIT_OK,
        "command": command,
        "exit_code": exit_code,
        "code": _CODES.get(exit_code, "failed"),
        "message": message,
        "conflicts": conflicts,
        "hint": _REFUSED_HINT if conflicts else None,
        "data": data or None,
        "warnings": warning_list,
        "text": text.strip(),
        "misata_version": __version__,
    }


def _write(envelope: Dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(envelope, indent=2, ensure_ascii=False, default=_jsonable) + "\n")
    sys.stdout.flush()


def _exit_code(exc: SystemExit) -> int:
    code = exc.code
    if code is None:
        return EXIT_OK
    if isinstance(code, int):
        return code
    return EXIT_FAILED


def _refuse_for_people(exc: BaseException) -> None:
    click.secho(str(exc), fg="red", err=True)
    click.echo(_REFUSED_HINT, err=True)


class MisataCommand(click.Command):
    """A command that speaks the envelope.

    Adds a ``--json`` flag unless the command opts out with
    ``json_output=False`` (a server whose stdout is a protocol, for one).
    """

    def __init__(self, *args: Any, json_output: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.json_output = json_output
        if json_output:
            self.params.append(click.Option(
                ["--json", "json_envelope"], is_flag=True, default=False, expose_value=False,
                callback=_mark_json,
                help=f"Print one JSON envelope instead of text (also: {JSON_ENV_VAR}=1)."))

    def _wants_json(self, args: Sequence[str]) -> bool:
        return self.json_output and ("--json" in args or _env_wants_json())

    def make_context(self, info_name: Optional[str], args: List[str],
                     parent: Optional[click.Context] = None, **extra: Any) -> click.Context:
        if not self._wants_json(args):
            return super().make_context(info_name, args, parent=parent, **extra)
        try:
            return super().make_context(info_name, list(args), parent=parent, **extra)
        except click.UsageError as exc:
            path = " ".join(filter(None, [parent.command_path if parent else None, info_name]))
            _write(_envelope(path or "misata", EXIT_USAGE, message=exc.format_message()))
            sys.exit(EXIT_USAGE)

    def invoke(self, ctx: click.Context) -> Any:
        if self.json_output and (ctx.meta.get(_JSON_META) or _env_wants_json()):
            return self._invoke_json(ctx)
        return self._invoke_for_people(ctx)

    def _invoke_for_people(self, ctx: click.Context) -> Any:
        from misata.feasibility import InfeasibleSchema

        try:
            return super().invoke(ctx)
        except InfeasibleSchema as exc:
            _refuse_for_people(exc)
            ctx.exit(EXIT_REFUSED)

    def _invoke_json(self, ctx: click.Context) -> Any:
        run = _Run()
        token = _CURRENT.set(run)
        buffer = io.StringIO()
        exit_code, message, error = EXIT_OK, None, None
        try:
            with warnings.catch_warnings(record=True) as caught, redirect_stdout(buffer):
                warnings.simplefilter("default")
                try:
                    super().invoke(ctx)
                except click.exceptions.Exit as exc:
                    exit_code = exc.exit_code
                except SystemExit as exc:
                    exit_code = _exit_code(exc)
                    if isinstance(exc.code, str):
                        message = exc.code
                except click.ClickException as exc:
                    exit_code = EXIT_USAGE if isinstance(exc, click.UsageError) else EXIT_FAILED
                    message, error = exc.format_message(), exc
                except Exception as exc:  # noqa: BLE001 - every failure becomes an envelope
                    exit_code = _classify(exc)
                    message, error = _describe(exc, exit_code), exc
        finally:
            _CURRENT.reset(token)
        _write(_envelope(ctx.command_path, exit_code, data=run.data,
                         message=message or run.message,
                         error=error, caught=caught, text=buffer.getvalue()))
        ctx.exit(exit_code)


def _mark_json(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    if value:
        ctx.meta[_JSON_META] = True


def _describe(exc: BaseException, exit_code: int) -> str:
    """The message, prefixed with the exception type when it was not expected."""
    from misata.exceptions import MisataError

    text = str(exc) or type(exc).__name__
    if exit_code == EXIT_FAILED and not isinstance(exc, MisataError):
        return f"{type(exc).__name__}: {text}"
    return text


class MisataGroup(click.Group):
    """A group whose commands and subgroups all speak the envelope."""

    command_class = MisataCommand
    group_class = type
