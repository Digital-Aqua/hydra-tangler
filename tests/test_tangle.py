""" Tangling fences into files: order, headers, tests, maps, purge. """

from pathlib import Path

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.outputs.python import PythonOutput
from hydra_tangler.writer import write_files


def _render(root: Path):
    return PythonOutput().render(load_book(root))


def test_fences_concatenate_in_document_order_and_skip_untagged(
    tmp_path: Path,
) -> None:
    write_chapter(
        tmp_path,
        "b.md",
        fence("python file=m.py", "b = 1")
        + fence("python file=m.py", "b2 = 1"),
    )
    write_chapter(
        tmp_path,
        "a.md",
        fence("python file=m.py", "a = 1")
        + "prose\n"
        + fence("python", "ignored = 1")
        + fence("python file=m.py", "", "a2 = 2"),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    text = rendered.files.data_for(Path("m.py"))
    assert text is not None
    assert text.decode() == (
        "# GENERATED from a.md, b.md - do not edit\n"
        "a = 1\n"
        "\n"
        "a2 = 2\n"
        "b = 1\n"
        "b2 = 1\n"
    )
    assert b"ignored" not in text


@pytest.mark.parametrize(
    ("name", "prefix", "suffix"),
    [
        ("a.py", "# ", ""),
        ("a.yaml", "# ", ""),
        ("a.yml", "# ", ""),
        ("a.toml", "# ", ""),
        ("Containerfile", "# ", ""),
        ("a.css", "/* ", " */"),
        ("a.js", "// ", ""),
        ("a.html", "<!-- ", " -->"),
    ],
)
def test_header_matches_the_extension(
    tmp_path: Path, name: str, prefix: str, suffix: str
) -> None:
    write_chapter(tmp_path, "c.md", fence(f"text file={name}", "body"))
    rendered = _render(tmp_path)
    data = rendered.files.data_for(Path(name))
    assert data is not None
    head = data.decode().splitlines()[0]
    assert head == f"{prefix}GENERATED from c.md - do not edit{suffix}"


def test_html_header_follows_a_doctype(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("html file=i.html", "<!doctype html>", "<p>"),
    )
    data = _render(tmp_path).files.data_for(Path("i.html"))
    assert data is not None
    lines = data.decode().splitlines()
    assert lines[0] == "<!doctype html>"
    assert lines[1].startswith("<!-- GENERATED")


def test_unknown_extension_is_an_error(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("text file=a.xyz", "body"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "no-comment"
    assert problem.line == 1
    assert problem.path == Path("c.md")


def test_bad_path_is_an_error(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=../x.py", "x = 1"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.diagnostics[0].code == "bad-path"
    assert rendered.diagnostics[0].line == 1


def test_test_fences_use_a_tests_root(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("python file=deck/mod.py", "a = 1")
        + fence("python file=test:deck/test_mod.py", "def test_a(): ...")
        + fence("python file=test_b.py", "x = 1")
        + fence("python file=test:test_b.py", "y = 2"),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    code = rendered.files.data_for(Path("deck/mod.py"))
    tests = rendered.files.data_for(Path("tests/deck/test_mod.py"))
    same_name = rendered.files.data_for(Path("test_b.py"))
    other = rendered.files.data_for(Path("tests/test_b.py"))
    assert code is not None and code.decode().endswith("a = 1\n")
    assert tests is not None and tests.decode().endswith("def test_a(): ...\n")
    assert same_name is not None and b"x = 1" in same_name
    assert other is not None and b"y = 2" in other
    assert rendered.files.data_for(Path("deck/test_mod.py")) is None


def test_escaping_test_path_is_an_error(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=test:../x.py", "x = 1"))
    rendered = _render(tmp_path)
    assert rendered.diagnostics[0].code == "bad-path"


def test_source_map_round_trip(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        "title\n\n" + fence("python file=m.py", "a = 1", "b = 2"),
    )
    rendered = _render(tmp_path)
    source_map = rendered.source_map
    assert source_map.markdown_at(Path("m.py"), 1) is not None
    origin = source_map.markdown_at(Path("m.py"), 3)
    assert origin is not None
    assert origin.path == Path("c.md")
    assert origin.line == 5
    outputs = source_map.output_at(Path("c.md"), 5)
    assert len(outputs) == 1
    assert outputs[0].path == Path("m.py")
    assert outputs[0].line == 3
    assert source_map.markdown_at(Path("m.py"), 99) is None


def test_second_run_leaves_mtime_and_purges_stale_files(tmp_path: Path) -> None:
    source = tmp_path / "src"
    target = tmp_path / "out"
    write_chapter(source, "c.md", fence("python file=pkg/old.py", "x = 1"))
    write_files(_render(source).files, target)
    old = target / "pkg" / "old.py"
    assert old.is_file()
    first_mtime = old.stat().st_mtime_ns
    write_files(_render(source).files, target)
    assert old.stat().st_mtime_ns == first_mtime
    extra = target / "notes.txt"
    _ = extra.write_text("keep me\n", encoding="utf-8")
    write_chapter(source, "c.md", fence("python file=new.py", "x = 1"))
    write_files(_render(source).files, target)
    assert not old.exists()
    assert not (target / "pkg").exists()
    assert (target / "new.py").is_file()
    assert extra.read_text(encoding="utf-8") == "keep me\n"


def test_failed_render_does_not_replace_files(tmp_path: Path) -> None:
    source = tmp_path / "src"
    target = tmp_path / "out"
    write_chapter(source, "c.md", fence("python file=m.py", "x = 1"))
    write_files(_render(source).files, target)
    write_chapter(source, "c.md", fence("text file=a.xyz", "body"))
    rendered = _render(source)
    assert rendered.diagnostics
    assert (target / "m.py").is_file()
