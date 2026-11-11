""" Unsaved buffer text fed into book loading. """

from pathlib import Path

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import UnreadableSource, load_book
from hydra_tangler.pipeline import BuildResult, build_book


def test_overrides_replace_disk_text_and_add_a_buffer(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", "# Disk\n")
    book = load_book(
        tmp_path,
        overrides={
            Path("a.md"): "# Buffer\n\n[x](nope.md)\n",
            Path("new.md"): "# New\n",
            Path("/tmp/outside.md"): "# no\n",
            Path(".secret.md"): "# no\n",
        },
    )
    assert [item.path.as_posix() for item in book.documents] == [
        "a.md",
        "new.md",
    ]
    first = book.documents[0]
    assert first.headings[0].slug == "buffer"
    assert first.links[0].target == "nope.md"


def test_dropped_overrides_are_warnings(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", "# A\n")
    book = load_book(
        tmp_path,
        overrides={
            Path("/tmp/outside.md"): "# no\n",
            Path("../escape.md"): "# no\n",
            Path("notes.txt"): "# no\n",
            Path(".secret.md"): "# no\n",
            Path("_build/x.md"): "# no\n",
        },
    )
    dropped = [
        item
        for item in book.diagnostics
        if item.code == "ignored-override"
    ]
    assert [item.path.as_posix() for item in dropped] == [
        "/tmp/outside.md",
        "../escape.md",
        "notes.txt",
        ".secret.md",
        "_build/x.md",
    ]
    assert all(
        item.line == 1 and item.severity == "warning" for item in dropped
    )
    assert [item.path.as_posix() for item in book.documents] == ["a.md"]


def test_unreadable_markdown_names_the_file(tmp_path: Path) -> None:
    path = tmp_path / "a.md"
    _ = path.write_bytes(b"\xff")
    with pytest.raises(UnreadableSource, match="a.md"):
        _ = load_book(tmp_path)


def test_build_book_tangles_override_text(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", fence("python file=m.py", "old = 1"))
    result = build_book(
        tmp_path,
        overrides={Path("a.md"): fence("python file=m.py", "new = 1")},
    )
    data = _python_bytes(result)
    assert data is not None
    assert b"new = 1" in data
    assert b"old = 1" not in data


def _python_bytes(result: BuildResult) -> bytes | None:
    for item in result.outputs:
        if item.name == "files":
            return item.rendered.files.data_for(Path("m.py"))
    return None
