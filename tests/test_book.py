""" Discovery and alphabetical document order. """

from pathlib import Path

from tests.books import write_chapter

from hydra_tangler.book import load_book


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


def test_discovery_skips_tool_directories_and_a_nested_target(
    tmp_path: Path,
) -> None:
    write_chapter(tmp_path, "keep.md", "# k\n")
    write_chapter(tmp_path, "src/also.md", "# s\n")
    write_chapter(tmp_path, "source/too.md", "# o\n")
    write_chapter(tmp_path, "_build/out.md", "# b\n")
    write_chapter(tmp_path, "node_modules/pkg.md", "# n\n")
    write_chapter(tmp_path, "__pycache__/c.md", "# p\n")
    write_chapter(tmp_path, ".hidden/h.md", "# h\n")
    write_chapter(tmp_path, "nested/stay.md", "# y\n")
    write_chapter(tmp_path, "nested/out/skip.md", "# x\n")
    book = load_book(tmp_path, target=tmp_path / "nested" / "out")
    assert [item.path.as_posix() for item in book.documents] == [
        "keep.md",
        "nested/stay.md",
        "source/too.md",
        "src/also.md",
    ]
