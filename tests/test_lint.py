""" Lint findings mapped through the source map. """

import json
from collections.abc import Sequence
from pathlib import Path

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.check.errors import LintError
from hydra_tangler.check.lint import lint_python, run_checker
from hydra_tangler.check.pyright import Pyright
from hydra_tangler.check.ruff import Ruff
from hydra_tangler.config import CheckSettings
from hydra_tangler.outputs.python import PythonOutput


def _rendered(root: Path, body: str):
    write_chapter(root, "c.md", fence("python file=m.py", body))
    return PythonOutput().render(load_book(root))


def test_maps_a_finding_onto_the_markdown_line(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "value = 1")
    shadow = tmp_path / "shadow"

    def run(argv: Sequence[str], cwd: Path) -> str:
        _ = cwd
        return json.dumps(
            {
                "generalDiagnostics": [
                    {
                        "file": argv[-1],
                        "severity": "error",
                        "message": "bad type",
                        "rule": "reportAssignmentType",
                        "range": {"start": {"line": 1, "character": 0}},
                    }
                ]
            }
        )

    found = lint_python(
        tmp_path,
        rendered,
        CheckSettings(),
        shadow=shadow,
        checkers=(Pyright(),),
        run=run,
    )
    assert (shadow / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert len(found) == 1
    assert found[0].path == Path("c.md")
    assert found[0].line == 2
    assert found[0].code == "basedpyright:reportAssignmentType"
    assert found[0].severity == "error"


def test_unmapped_finding_uses_the_first_fence(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "value = 1")

    def run(argv: Sequence[str], cwd: Path) -> str:
        _ = (argv, cwd)
        return json.dumps(
            [
                {
                    "filename": "m.py",
                    "code": "F401",
                    "message": "unused",
                    "location": {"row": 40, "column": 1},
                }
            ]
        )

    found = lint_python(
        tmp_path,
        rendered,
        CheckSettings(),
        shadow=tmp_path / "shadow",
        checkers=(Ruff(),),
        run=run,
    )
    assert len(found) == 1
    assert found[0].line == 1
    assert found[0].code == "ruff:F401"
    assert found[0].severity == "warning"


def test_a_missing_checker_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LintError, match="cannot run"):
        _ = run_checker(["hydra-tangler-missing-tool"], tmp_path)


@pytest.mark.slow
def test_basedpyright_reports_a_real_error(tmp_path: Path) -> None:
    project = Path(__file__).resolve().parents[1]
    rendered = _rendered(tmp_path, "value: int = 'no'")
    settings = CheckSettings(
        pyright=(
            "uv",
            "run",
            "--project",
            str(project),
            "basedpyright",
            "--outputjson",
        )
    )
    found = lint_python(
        tmp_path,
        rendered,
        settings,
        shadow=tmp_path / "shadow",
        checkers=(Pyright(),),
    )
    assert any(
        item.path == Path("c.md") and item.code.startswith("basedpyright")
        for item in found
    )
