"""Lint findings mapped through the source map."""

import json
import subprocess
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast, final

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.check.errors import LintError
from hydra_tangler.check.lint import lint_python, map_type_reports, run_checker
from hydra_tangler.check.pyright_server import (
    BasedpyrightCheck,
    TypeReport,
    bundled_command,
    configuration_result,
    initialize_params,
    parse_type_diagnostic,
)
from hydra_tangler.check.ruff import Ruff
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.fences.exemptions import Exclusion, rules_for
from hydra_tangler.fences.plaintext import PlainText
from hydra_tangler.fences.python import Python
from hydra_tangler.model import Diagnostic
from hydra_tangler.outputs.files import FilesOutput


@final
class _Reports:
    """A type checker that returns a fixed list of findings."""

    def __init__(self, reports: tuple[TypeReport, ...]) -> None:
        self._reports: tuple[TypeReport, ...] = reports

    def check(
        self,
        book: Path,
        shadow: Path,
        files: Mapping[Path, str],
    ) -> tuple[TypeReport, ...]:
        _ = (book, shadow, files)
        return self._reports


def _rendered(root: Path, *body: str):
    write_chapter(root, "c.md", fence("python file=m.py", *body))
    return FilesOutput().render(load_book(root))


def test_maps_a_finding_onto_the_markdown_line(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "value = 1")
    shadow = tmp_path / "shadow"
    report = TypeReport(
        "m.py",
        1,
        0,
        1,
        5,
        "error",
        "reportAssignmentType",
        "bad type",
    )
    found = lint_python(
        tmp_path,
        rendered,
        CheckerCommands(),
        shadow=shadow,
        checkers=(),
        typecheck=_Reports((report,)),
    )
    assert (shadow / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert len(found) == 1
    assert found[0].path == Path("c.md")
    assert found[0].line == 2
    assert found[0].start_character == 0
    assert found[0].end_character == 5
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
        CheckerCommands(),
        shadow=tmp_path / "shadow",
        checkers=(Ruff(),),
        run=run,
    )
    assert len(found) == 1
    assert found[0].line == 1
    assert found[0].code == "ruff:F401"
    assert found[0].severity == "warning"


def test_an_unmapped_finding_stays_on_the_output_path(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "value = 1")
    reports = (
        TypeReport("", 3, 0, 3, 1, "error", "", "nowhere"),
        TypeReport(
            "/tmp/not-in-shadow.py",
            1,
            0,
            1,
            1,
            "warning",
            "",
            "outside",
        ),
    )
    found = map_type_reports(reports, tmp_path / "shadow", rendered.source_map)
    places = [(item.path.as_posix(), item.line, item.message) for item in found]
    assert places == [
        (".", 4, "nowhere"),
        ("/tmp/not-in-shadow.py", 2, "outside"),
    ]
    assert all(
        item.code == "unmapped-finding" and item.severity == "warning"
        for item in found
    )


def test_no_python_output_is_silent(tmp_path: Path) -> None:
    found = lint_python(tmp_path, None, CheckerCommands())
    assert found == ()


def test_information_and_hint_become_warnings() -> None:
    info = parse_type_diagnostic(
        "file:///m.py",
        {"severity": 3, "message": "info", "range": {"start": {"line": 0}}},
    )
    hint = parse_type_diagnostic(
        "file:///m.py",
        {
            "severity": "hint",
            "message": "hint",
            "range": {"start": {"line": 1}},
        },
    )
    assert info is not None and hint is not None
    assert info.severity == "warning"
    assert hint.severity == "warning"
    assert info.message == "info"
    assert hint.message == "hint"


def test_rules_for_keeps_one_checker_in_order() -> None:
    exclusions = (
        Exclusion("ruff", ("I001", "F401")),
        Exclusion("basedpyright", ("reportUnusedImport",)),
        Exclusion("ruff", ("I001", "E501")),
    )
    assert rules_for(exclusions, "ruff") == ("I001", "F401", "E501")
    assert rules_for(exclusions, "eslint") == ()
    assert PlainText.exclusions == ()
    assert rules_for(Python.exclusions, "ruff") == ()


def test_ruff_command_drops_import_sorting(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "from typing import Any", "import os")
    seen: list[Sequence[str]] = []

    def run(argv: Sequence[str], cwd: Path) -> str:
        _ = cwd
        seen.append(argv)
        return "[]"

    found = lint_python(
        tmp_path,
        rendered,
        CheckerCommands(),
        shadow=tmp_path / "shadow",
        checkers=(Ruff(),),
        run=run,
    )
    assert found == ()
    config = seen[0].index("--config")
    text = Path(seen[0][config + 1]).read_text(encoding="utf-8")
    assert 'ignore = ["I001", "RUF100"]' in text
    assert "--ignore" not in seen[0]


def test_bundled_basedpyright_is_not_the_book_environment() -> None:
    command = bundled_command()
    assert command[1:] == ("--stdio",)
    assert command[0].endswith("basedpyright-langserver")
    assert "uv" not in command
    params = initialize_params(Path("/tmp/book"))
    assert params["rootUri"] == Path("/tmp/book").resolve().as_uri()


def test_configuration_names_the_venv_and_the_shadow(tmp_path: Path) -> None:
    python = tmp_path / ".venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    _ = python.write_text("", encoding="utf-8")
    sections = (
        {"section": "python"},
        {"section": "basedpyright"},
        {"section": "other"},
    )
    result = configuration_result(tmp_path, sections)
    written = tmp_path / ".hydra" / "pyrightconfig.json"
    assert result[0] == {"pythonPath": str(python)}
    assert result[1] == {
        "analysis": {
            "diagnosticMode": "openFilesOnly",
            "configFilePath": str(written),
        }
    }
    payload = cast(
        dict[str, object],
        json.loads(written.read_text(encoding="utf-8")),
    )
    shadow = str((tmp_path / ".hydra" / "shadow").resolve())
    assert payload["typeCheckingMode"] == "recommended"
    assert payload["reportUnnecessaryTypeIgnoreComment"] == "none"
    assert payload["include"] == [shadow]
    assert result[2] is None


def test_configuration_omits_a_missing_venv(tmp_path: Path) -> None:
    result = configuration_result(tmp_path, [{"section": "python"}])
    assert result == [{}]


def test_ruff_keeps_other_findings_on_an_unsorted_import(
    tmp_path: Path,
) -> None:
    project = Path(__file__).resolve().parents[1]
    rendered = _rendered(
        tmp_path,
        "from typing import Any",
        "import os",
        "",
        "x",
    )
    settings = CheckerCommands(
        ruff=(
            "uv",
            "run",
            "--project",
            str(project),
            "ruff",
            "check",
            "--output-format",
            "json",
        )
    )
    found = lint_python(
        tmp_path,
        rendered,
        settings,
        shadow=tmp_path / "shadow",
        checkers=(Ruff(),),
    )
    codes = [item.code for item in found]
    assert "ruff:I001" not in codes
    assert "ruff:F821" in codes
    assert {item.severity for item in found} == {"warning"}


def test_ruff_json_error_severity_stays_a_warning() -> None:
    payload = json.dumps(
        [
            {
                "filename": "m.py",
                "code": "F401",
                "message": "`os` imported but unused",
                "severity": "error",
                "location": {"row": 1, "column": 1},
            }
        ]
    )
    found = Ruff().read(payload)
    assert len(found) == 1
    assert found[0].code == "ruff:F401"
    assert found[0].severity == "warning"


def test_a_non_object_finding_is_an_error() -> None:
    with pytest.raises(LintError, match="not an object"):
        _ = Ruff().read(json.dumps([1]))


def test_a_bad_type_diagnostic_is_skipped() -> None:
    assert parse_type_diagnostic("file:///m.py", "bad") is None


def test_a_missing_checker_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(LintError, match="cannot run"):
        _ = run_checker(["hydra-tangler-missing-tool"], tmp_path)


def test_a_dead_langserver_is_an_error(tmp_path: Path) -> None:
    rendered = _rendered(tmp_path, "value: int = 'no'")
    checker = BasedpyrightCheck(
        (sys.executable, "-c", "raise SystemExit(1)"),
        tmp_path,
    )
    with pytest.raises(LintError):
        _ = lint_python(
            tmp_path,
            rendered,
            CheckerCommands(),
            shadow=tmp_path / "shadow",
            checkers=(),
            typecheck=checker,
        )


def _body() -> tuple[str, ...]:
    return (
        "import onlyinvendor",
        "class Box:",
        "    def __init__(self, n: int) -> None:",
        "        pass",
        "Box('no')",
        "value: int = 'no'",
    )


def _vendor(root: Path) -> None:
    venv = root / ".venv"
    _ = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=True,
        capture_output=True,
    )
    site = next((venv / "lib").glob("python*/site-packages"))
    _ = (site / "onlyinvendor.py").write_text("VALUE = 1\n", encoding="utf-8")


def _typecheck(root: Path, *body: str) -> tuple[Diagnostic, ...]:
    rendered = _rendered(root, *body)
    checker = BasedpyrightCheck((), root)
    try:
        return lint_python(
            root,
            rendered,
            CheckerCommands(),
            shadow=root / "shadow",
            checkers=(),
            typecheck=checker,
        )
    finally:
        checker.close()


@pytest.mark.slow
def test_unnecessary_type_ignore_stays_quiet(tmp_path: Path) -> None:
    found = _typecheck(tmp_path, "value = 1  # pyright: ignore")
    codes = {item.code for item in found}
    assert "basedpyright:reportUnnecessaryTypeIgnoreComment" not in codes


@pytest.mark.slow
def test_project_can_report_unnecessary_type_ignore(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.basedpyright]\n"
        + 'reportUnnecessaryTypeIgnoreComment = "warning"\n',
        encoding="utf-8",
    )
    found = _typecheck(tmp_path, "value = 1  # pyright: ignore")
    codes = {item.code for item in found}
    assert "basedpyright:reportUnnecessaryTypeIgnoreComment" in codes


@pytest.mark.slow
def test_basedpyright_uses_the_book_venv(tmp_path: Path) -> None:
    _vendor(tmp_path)
    found = _typecheck(tmp_path, *_body())
    codes = {item.code for item in found}
    assert "basedpyright:reportArgumentType" in codes
    assert "basedpyright:reportAssignmentType" in codes
    assert "basedpyright:reportMissingImports" not in codes
    argument = next(
        item for item in found if item.code == "basedpyright:reportArgumentType"
    )
    assert argument.start_character is not None
    assert argument.start_character > 0
    _ = argument


@pytest.mark.slow
def test_basedpyright_without_a_venv_misses_the_import(tmp_path: Path) -> None:
    found = _typecheck(tmp_path, *_body())
    codes = {item.code for item in found}
    assert "basedpyright:reportMissingImports" in codes
    assert "basedpyright:reportArgumentType" in codes
    assert "basedpyright:reportAssignmentType" in codes
