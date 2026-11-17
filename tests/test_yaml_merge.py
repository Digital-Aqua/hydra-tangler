"""YAML fences that share a path are deep-merged."""

from pathlib import Path

from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.outputs.files import FilesOutput


def _render(root: Path):
    return FilesOutput().render(load_book(root))


def _text(root: Path, name: str) -> str:
    rendered = _render(root)
    assert rendered.diagnostics == ()
    data = rendered.files.data_for(Path(name))
    assert data is not None
    return data.decode()


def test_mappings_merge_and_sequences_concatenate(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence(
            "yaml file=a.yaml",
            "obj:",
            "  a: 1",
            "  nested:",
            "    x: 1",
            "items:",
            "  - 1",
        ),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence(
            "yaml file=a.yaml",
            "obj:",
            "  b: 2",
            "  nested:",
            "    y: 2",
            "items:",
            "  - 2",
        ),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    data = rendered.files.data_for(Path("a.yaml"))
    assert data is not None
    text = data.decode()
    assert text == (
        "# GENERATED from a.md, b.md - do not edit\n"
        "obj:\n"
        "  a: 1\n"
        "  nested:\n"
        "    x: 1\n"
        "    y: 2\n"
        "  b: 2\n"
        "items:\n"
        "- 1\n"
        "- 2\n"
    )
    records = tuple(
        record
        for record in rendered.source_map.records
        if record.output.path == Path("a.yaml")
    )
    assert {record.markdown.path for record in records} == {Path("a.md")}
    assert {record.markdown.line for record in records} == {1}


def test_later_scalar_wins(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("yaml file=a.yaml", "n: 1", "s: 1", "z: 1"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("yaml file=a.yaml", "n: 2", 's: "1"', "z: null"),
    )
    assert _text(tmp_path, "a.yaml") == (
        "# GENERATED from a.md, b.md - do not edit\nn: 2\ns: '1'\nz: null\n"
    )


def test_mapping_sequence_clash_writes_nothing(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("yaml file=a.yaml", "widget:", "  kind: map"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("yaml file=a.yaml", "widget:", "  - item"),
    )
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.source_map.records == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "yaml-merge"
    assert problem.severity == "error"
    assert problem.path == Path("b.md")
    assert problem.line == 1


def test_later_alias_resolves_an_earlier_anchor(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("yaml file=a.yaml", "defs: &defs", "  a: 1"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("yaml file=a.yaml", "use: *defs"),
    )
    text = _text(tmp_path, "a.yaml")
    assert "&" not in text
    assert text == (
        "# GENERATED from a.md, b.md - do not edit\n"
        "defs:\n"
        "  a: 1\n"
        "use:\n"
        "  a: 1\n"
    )


def test_merged_anchor_is_retargeted_before_alias_resolution(
    tmp_path: Path,
) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("yaml file=a.yaml", "defs: &defs", "  a: 1"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("yaml file=a.yaml", "defs:", "  b: 2", "use: *defs"),
    )
    text = _text(tmp_path, "a.yaml")
    assert "&" not in text
    assert "*" not in text
    assert text == (
        "# GENERATED from a.md, b.md - do not edit\n"
        "defs:\n"
        "  a: 1\n"
        "  b: 2\n"
        "use:\n"
        "  a: 1\n"
        "  b: 2\n"
    )


def test_duplicate_anchor_writes_nothing(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("yaml file=a.yaml", "a: &item 1"))
    write_chapter(tmp_path, "b.md", fence("yaml file=a.yaml", "b: &item 2"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.source_map.records == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "yaml-merge"
    assert problem.severity == "error"
    assert problem.path == Path("b.md")


def test_unknown_alias_writes_nothing(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("yaml file=a.yaml", "a: 1"))
    write_chapter(tmp_path, "b.md", fence("yaml file=a.yaml", "use: *missing"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.source_map.records == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "yaml-syntax"
    assert problem.severity == "error"
    assert problem.path == Path("b.md")


def test_broken_body_reports_yaml_syntax_on_that_line(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("yaml file=a.yaml", "ok: 1"))
    write_chapter(tmp_path, "b.md", fence("yaml file=a.yaml", "a: ["))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.source_map.records == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "yaml-syntax"
    assert problem.severity == "error"
    assert problem.path == Path("b.md")
    assert problem.line == 2


def test_one_fence_is_copied_with_anchors(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        "intro\n\n" + fence("yaml file=a.yaml", "defs: &defs", "  a: 1"),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    data = rendered.files.data_for(Path("a.yaml"))
    assert data is not None
    assert data.decode() == (
        "# GENERATED from a.md - do not edit\ndefs: &defs\n  a: 1\n"
    )
    origin = rendered.source_map.markdown_at(Path("a.yaml"), 3)
    assert origin is not None
    assert origin.path == Path("a.md")
    assert origin.line == 5


def test_openapi_tangler_yaml_participates(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("openapi file=a.yaml tangler=yaml", "title: one"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("openapi file=a.yaml tangler=yaml", "version: two"),
    )
    assert _text(tmp_path, "a.yaml") == (
        "# GENERATED from a.md, b.md - do not edit\ntitle: one\nversion: two\n"
    )


def test_python_beside_yaml_is_still_concatenated(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("python file=m.py", "a = 1") + fence("yaml file=a.yaml", "a: 1"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("python file=m.py", "b = 1") + fence("yaml file=a.yaml", "b: 2"),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    python = rendered.files.data_for(Path("m.py"))
    yaml_file = rendered.files.data_for(Path("a.yaml"))
    assert python is not None
    assert yaml_file is not None
    assert python.decode() == (
        "# GENERATED from a.md, b.md - do not edit\na = 1\nb = 1\n"
    )
    assert yaml_file.decode() == (
        "# GENERATED from a.md, b.md - do not edit\na: 1\nb: 2\n"
    )


def test_mixed_joiners_write_nothing(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("yaml file=shared.txt", "a: 1"))
    write_chapter(tmp_path, "b.md", fence("python file=shared.txt", "x = 1"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.source_map.records == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "mixed-join"
    assert problem.severity == "error"
    assert problem.path == Path("b.md")
    assert problem.line == 1


def test_root_null_adds_nothing(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("yaml file=a.yaml", "null"))
    write_chapter(tmp_path, "b.md", fence("yaml file=a.yaml", "a: 1"))
    assert _text(tmp_path, "a.yaml") == (
        "# GENERATED from a.md, b.md - do not edit\na: 1\n"
    )


def test_alias_cycle_is_yaml_syntax(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("yaml file=a.yaml", "loop: &loop", "  self: *loop"),
    )
    write_chapter(tmp_path, "b.md", fence("yaml file=a.yaml", "extra: 1"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "yaml-syntax"
    assert problem.severity == "error"
    assert problem.path == Path("a.md")
