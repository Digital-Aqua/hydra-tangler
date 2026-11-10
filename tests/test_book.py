""" Discovery and alphabetical document order. """

from pathlib import Path

from tests.books import write_chapter

from hydra_tangler.book import default_source, load_book


def test_documents_are_alphabetical_by_relative_path(tmp_path: Path) -> None:
    write_chapter(tmp_path, "b.md", "# b\n")
    write_chapter(tmp_path, "a/c.md", "# c\n")
    write_chapter(tmp_path, "10.md", "# ten\n")
    write_chapter(tmp_path, "2.md", "# two\n")
    write_chapter(tmp_path, "a.md", "# a\n")
    write_chapter(tmp_path, ".notes/hidden.md", "# hidden\n")
    book = load_book(tmp_path)
    assert [item.path.as_posix() for item in book.documents] == [
        "10.md",
        "2.md",
        "a.md",
        "a/c.md",
        "b.md",
    ]


def test_default_source_prefers_src_then_source(tmp_path: Path) -> None:
    assert default_source(tmp_path) == tmp_path
    (tmp_path / "source").mkdir()
    assert default_source(tmp_path) == tmp_path / "source"
    (tmp_path / "src").mkdir()
    assert default_source(tmp_path) == tmp_path / "src"
