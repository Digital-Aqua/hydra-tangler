""" Fence classes, attribute overrides, and the tag registry. """

from pathlib import Path
from typing import ClassVar

import pytest
from tests.books import fence, write_chapter
from typer.testing import CliRunner

from hydra_tangler.book import load_book
from hydra_tangler.fences import FenceLoadError, load_fences, registry_from
from hydra_tangler.fences.plaintext import PlainText
from hydra_tangler.main import app
from hydra_tangler.outputs.files import FilesOutput

runner = CliRunner()


def _render(root: Path):
    return FilesOutput().render(load_book(root))


def test_a_subclass_is_a_new_language(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Rust(PlainText):
        """ Rust fences use slash comments. """

        tags: ClassVar[tuple[str, ...]] = ("rust",)
        comment_prefix: ClassVar[str] = "// "

    classes = {type(handler) for handler in load_fences().values()}
    monkeypatch.setattr(
        "hydra_tangler.outputs.files.load_fences",
        lambda: registry_from((*classes, Rust)),
    )
    write_chapter(tmp_path, "c.md", fence("rust file=a.rs", "fn main() {}"))
    data = _render(tmp_path).files.data_for(Path("a.rs"))
    assert data is not None
    assert data.decode().startswith("// GENERATED from c.md - do not edit\n")


def test_tangler_text_overrides_an_unknown_tag(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("rust file=myfile.rs comment='// ' tangler=text", "fn main() {}"),
    )
    rendered = _render(tmp_path)
    data = rendered.files.data_for(Path("myfile.rs"))
    assert rendered.diagnostics == ()
    assert data is not None
    assert data.decode().startswith("// GENERATED from c.md - do not edit\n")


def test_unknown_tag_warns_and_skips(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("rust file=a.rs", "fn main() {}"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "unsupported-language"
    assert problem.severity == "warning"
    assert "rust" in problem.message
    assert "a.rs" in problem.message
    assert "tangler=text" in problem.message


def test_missing_tag_is_an_unsupported_language(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("file=a.rs", "fn main() {}"))
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    assert rendered.diagnostics[0].code == "unsupported-language"


def test_unknown_language_exits_zero(tmp_path: Path) -> None:
    source = tmp_path / "notes"
    target = tmp_path / "out"
    write_chapter(source, "c.md", fence("rust file=a.rs", "fn main() {}"))
    result = runner.invoke(
        app,
        ["tangle", "--output", "files", str(source), str(target)],
    )
    assert result.exit_code == 0, result.output
    reported = (result.stderr or "") + result.output
    assert "unsupported-language" in reported
    assert not (target / "a.rs").exists()


def test_block_comment_override(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("text file=a.c comment='/* ' comment_end=' */'", "int x;"),
    )
    data = _render(tmp_path).files.data_for(Path("a.c"))
    assert data is not None
    assert data.decode().splitlines()[0] == (
        "/* GENERATED from c.md - do not edit */"
    )


def test_header_false_omits_the_header(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("python file=m.py header=false", "x = 1"),
    )
    data = _render(tmp_path).files.data_for(Path("m.py"))
    assert data is not None
    assert data.decode() == "x = 1\n"


def test_fence_without_file_is_silent(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("python", "ignored = 1")
        + fence("python tangler=text", "also = 1")
        + fence("python file=m.py", "x = 1"),
    )
    rendered = _render(tmp_path)
    assert rendered.diagnostics == ()
    data = rendered.files.data_for(Path("m.py"))
    assert data is not None
    assert b"ignored" not in data
    assert b"also" not in data


def test_unknown_tangler_warns_and_skips(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("python file=m.py tangler=nope", "x = 1"),
    )
    rendered = _render(tmp_path)
    assert rendered.files.files == ()
    problem = rendered.diagnostics[0]
    assert problem.code == "unknown-tangler"
    assert "nope" in problem.message


def test_mixed_comment_styles_keep_the_first(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("python file=m.py", "a = 1"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("python file=m.py comment='// '", "b = 1"),
    )
    rendered = _render(tmp_path)
    data = rendered.files.data_for(Path("m.py"))
    assert data is not None
    text = data.decode()
    assert text.startswith("# GENERATED from a.md, b.md - do not edit\n")
    assert "b = 1" in text
    problem = rendered.diagnostics[0]
    assert problem.code == "mixed-comment-styles"
    assert problem.severity == "warning"
    assert problem.path == Path("b.md")


def test_duplicate_tag_is_a_load_error() -> None:
    class Extra(PlainText):
        """ A second class claiming the text tag. """

        tags: ClassVar[tuple[str, ...]] = ("text",)

    with pytest.raises(FenceLoadError, match="'text'"):
        _ = registry_from((PlainText, Extra))
