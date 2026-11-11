""" Parse ``ruff check --output-format json`` into reported findings.

Ruff's JSON has no severity, so findings are warnings: they are
printed, and they do not by themselves fail ``check``. A present
``severity`` of ``error`` is kept. This module does not start ruff.
"""

from pathlib import Path
from typing import cast

from hydra_tangler.check.errors import LintError
from hydra_tangler.check.json_text import json_value
from hydra_tangler.check.reported import Reported
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.model import Severity


class Ruff:
    """ The ruff checker. """

    name: str = "ruff"

    def configured(self, commands: CheckerCommands) -> tuple[str, ...]:
        """ The ruff argv from the caller, if one was given. """
        return commands.ruff

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
            "ruff",
            "check",
            "--output-format",
            "json",
        )

    def read(self, stdout: str) -> tuple[Reported, ...]:
        """ Read the JSON array ruff prints. """
        items = _as_list(json_value(stdout))
        if items is None:
            raise LintError("ruff output was not JSON")
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
        raise LintError("ruff finding was not an object")
    location = _as_dict(record.get("location"))
    code = record.get("code")
    label = "ruff" if not isinstance(code, str) or not code else f"ruff:{code}"
    return Reported(
        str(record.get("filename", "")),
        _row(location),
        _severity(record.get("severity")),
        label,
        _message(record.get("message")),
    )


def _row(location: dict[str, object] | None) -> int:
    if location is None:
        return 1
    raw = location.get("row", 1)
    if isinstance(raw, int) and raw > 0:
        return raw
    return 1


def _severity(value: object) -> Severity:
    if value == "error":
        return "error"
    return "warning"


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
