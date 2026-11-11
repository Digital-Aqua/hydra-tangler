""" Parse basedpyright ``--outputjson`` into reported findings.

The command defaults to ``uv run`` inside the user project so the
project's checker and environment are used. This module does not
start the process.
"""

from pathlib import Path
from typing import cast

from hydra_tangler.check.errors import LintError
from hydra_tangler.check.json_text import json_value
from hydra_tangler.check.reported import Reported
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.model import Severity


class Pyright:
    """ The basedpyright checker. """

    name: str = "basedpyright"

    def configured(self, commands: CheckerCommands) -> tuple[str, ...]:
        """ The basedpyright argv from the caller, if one was given. """
        return commands.pyright

    def argv(
        self,
        project: Path,
        configured: tuple[str, ...],
    ) -> tuple[str, ...]:
        """ Use ``configured`` or the default ``uv run`` command. """
        if configured:
            return configured
        return (
            "uv",
            "run",
            "--project",
            str(project),
            "basedpyright",
            "--outputjson",
        )

    def read(self, stdout: str) -> tuple[Reported, ...]:
        """ Read ``generalDiagnostics`` from the JSON payload. """
        payload = _as_dict(json_value(stdout))
        if payload is None:
            raise LintError("basedpyright output was not JSON")
        if "generalDiagnostics" not in payload:
            raise LintError("basedpyright output has no generalDiagnostics")
        items = _as_list(payload.get("generalDiagnostics"))
        if items is None:
            raise LintError("basedpyright generalDiagnostics was not a list")
        return _keep(items)


def _keep(items: list[object]) -> tuple[Reported, ...]:
    found: list[Reported] = []
    for item in items:
        one = _finding(item)
        if one is not None:
            found.append(one)
    return tuple(found)


def _finding(item: object) -> Reported | None:
    record = _as_dict(item)
    if record is None:
        raise LintError("basedpyright diagnostic was not an object")
    severity = _severity(record.get("severity"))
    if severity is None:
        return None
    start = _start(record.get("range"))
    rule = record.get("rule")
    code = "basedpyright" if not isinstance(rule, str) or not rule else (
        f"basedpyright:{rule}"
    )
    return Reported(
        str(record.get("file", "")),
        _line(start),
        severity,
        code,
        _message(record.get("message")),
    )


def _start(value: object) -> dict[str, object] | None:
    span = _as_dict(value)
    if span is None:
        return None
    return _as_dict(span.get("start"))


def _line(start: dict[str, object] | None) -> int:
    if start is None:
        return 1
    raw = start.get("line", 0)
    if isinstance(raw, int):
        return raw + 1
    return 1


def _severity(value: object) -> Severity | None:
    if value == "error":
        return "error"
    if value in ("warning", "information", "hint"):
        return "warning"
    return None


def _message(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None
