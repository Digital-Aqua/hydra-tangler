""" The tangle and where commands. """

from pathlib import Path

import pytest
from tests.books import fence, write_chapter
from typer.testing import CliRunner

from hydra_tangler.main import app

runner = CliRunner()


def test_watch_reports_an_unreadable_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _ = (tmp_path / "a.md").write_bytes(b"\xff")
    result = runner.invoke(app, ["watch"])
    assert result.exit_code == 1
    assert "error:" in result.output
    assert "a.md" in result.output


def test_watch_reports_a_watcher_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_chapter(tmp_path, "a.md", "# A\n")

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("too many watches")

    monkeypatch.setattr("hydra_tangler.main.watch_markdown", boom)
    result = runner.invoke(app, ["watch"])
    assert result.exit_code == 1
    assert "error: too many watches" in result.output


def test_tangle_writes_the_default_build_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_chapter(tmp_path, "c.md", fence("python file=m.py", "x = 1"))
    result = runner.invoke(app, ["tangle"])
    assert result.exit_code == 0, result.output
    built = tmp_path / "_build" / "m.py"
    assert built.is_file()
    assert built.read_text(encoding="utf-8").endswith("x = 1\n")


def test_tangle_accepts_source_target_and_output(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "built"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    result = runner.invoke(
        app,
        ["tangle", "--output", "files", str(source), str(target)],
    )
    assert result.exit_code == 0, result.output
    assert (target / "m.py").is_file()
    assert not (tmp_path / "_build").exists()


def test_errors_print_diagnostics_and_leave_the_tree(tmp_path: Path) -> None:
    source = tmp_path / "src"
    target = tmp_path / "out"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    first = runner.invoke(
        app,
        ["tangle", "--output", "files", str(source), str(target)],
    )
    assert first.exit_code == 0, first.output
    write_chapter(source, "c.md", "ok\n```python\nx\n")
    result = runner.invoke(
        app,
        ["tangle", "--output", "files", str(source), str(target)],
    )
    assert result.exit_code == 1
    reported = (result.stderr or "") + result.output
    assert "c.md:2: error unclosed-fence: fence is never closed" in reported
    assert (target / "m.py").is_file()


def test_output_option_can_be_repeated(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "built"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    result = runner.invoke(
        app,
        [
            "tangle",
            "--output",
            "files",
            "--output",
            "htmldocs",
            str(source),
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (target / "m.py").is_file()
    assert (target / "sourcemap.json").is_file()
    assert any((target / "docs").rglob("*.html"))


def test_collision_writes_nothing(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "built"
    write_chapter(source, "c.md", fence("python file=docs/x.txt", "x = 1"))
    result = runner.invoke(app, ["tangle", str(source), str(target)])
    assert result.exit_code == 1
    reported = (result.stderr or "") + result.output
    assert "output-collision" in reported
    assert "docs/x.txt" in reported
    assert not target.exists()


def test_no_sourcemap_skips_the_map_file(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "built"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    result = runner.invoke(
        app,
        [
            "tangle",
            "--no-sourcemap",
            "--output",
            "files",
            str(source),
            str(target),
        ],
    )
    assert result.exit_code == 0, result.output
    assert (target / "m.py").is_file()
    assert not (target / "sourcemap.json").exists()


def test_where_maps_output_lines(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    write_chapter(
        tmp_path,
        "c.md",
        "title\n\n" + fence("python file=m.py", "a = 1", "b = 2"),
    )
    built = runner.invoke(app, ["tangle"])
    assert built.exit_code == 0, built.output
    direct = runner.invoke(app, ["where", "m.py:3"])
    assert direct.exit_code == 0, direct.output
    assert direct.stdout.strip() == "c.md:5"
    nested = runner.invoke(app, ["where", "_build/m.py:2"])
    assert nested.exit_code == 0, nested.output
    assert nested.stdout.strip() == "c.md:4"
    missing = runner.invoke(app, ["where", "m.py:99"])
    assert missing.exit_code == 1
    assert "not in the tangle" in (missing.stderr or "") + missing.output


def test_where_rejects_a_bad_spec(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["where", "m.py"])
    assert result.exit_code == 1
    assert "expected FILE:LINE" in (result.stderr or "") + result.output
