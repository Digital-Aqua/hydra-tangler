""" The check and watch commands, and tangle's link warnings. """

import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest
from tests.books import fence, write_chapter
from typer.testing import CliRunner

from hydra_tangler.main import app

runner = CliRunner()


def test_tangle_prints_dead_links_after_writing(tmp_path: Path) -> None:
    source = tmp_path / "src"
    target = tmp_path / "out"
    write_chapter(
        source,
        "c.md",
        "See [gone](missing.md).\n\n" + fence("python file=m.py", "x = 1"),
    )
    result = runner.invoke(
        app,
        ["tangle", "--output", "files", str(source), str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "m.py").is_file()
    reported = (result.stderr or "") + result.output
    assert "c.md:1: warning dead-link:" in reported


def test_check_json_keeps_warnings_successful(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    write_chapter(source, "a.md", "See [gone](missing.md).\n")
    result = runner.invoke(app, ["check", "--json", str(source)])
    assert result.exit_code == 0, result.output
    payload = cast(object, json.loads(result.stdout))
    assert isinstance(payload, list)
    first = cast(dict[str, object], payload[0])
    assert first["code"] == "dead-link"
    assert first["severity"] == "warning"
    assert first["path"] == "a.md"


def test_check_exits_on_error_severity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_chapter(tmp_path, "c.md", "```python\nx\n")
    result = runner.invoke(app, ["check"])
    assert result.exit_code == 1
    reported = (result.stderr or "") + result.output
    assert "error unclosed-fence" in reported


def test_check_rejects_an_unbalanced_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_chapter(tmp_path, "a.md", "# a\n")
    result = runner.invoke(app, ["check", "--ruff-command", "'unterminated"])
    assert result.exit_code == 1
    reported = (result.stderr or "") + result.output
    assert "bad command" in reported


def test_watch_tangles_then_waits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "notes" / "built"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    seen: dict[str, Path] = {}
    ignored: list[tuple[Path, ...]] = []

    def fake(
        directory: Path,
        on_change: Callable[[], None],
        ignore: tuple[Path, ...] = (),
        batches: object = None,
    ) -> None:
        _ = batches
        seen["directory"] = directory
        ignored.append(ignore)
        on_change()

    monkeypatch.setattr("hydra_tangler.main.watch_markdown", fake)
    result = runner.invoke(
        app,
        ["watch", "--output", "files", str(source), str(target)],
    )
    assert result.exit_code == 0, result.output
    assert seen["directory"] == source
    assert target.resolve() in ignored[0]
    assert (target / "m.py").is_file()
