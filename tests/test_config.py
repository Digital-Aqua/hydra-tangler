""" Nothing under src reads a project file for Hydra settings. """

import re
from pathlib import Path

_TOMLLIB = re.compile(r"^\s*(?:import tomllib\b|from tomllib\b)", re.MULTILINE)


def test_source_does_not_read_pyproject() -> None:
    root = Path(__file__).resolve().parents[1] / "src"
    offenders: list[str] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        if _TOMLLIB.search(text) or '"pyproject.toml"' in text:
            offenders.append(path.relative_to(root).as_posix())
        if "'pyproject.toml'" in text:
            offenders.append(path.relative_to(root).as_posix())
    assert offenders == []
