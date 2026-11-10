""" Unsaved buffer text fed into book loading. """

from pathlib import Path

from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
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


def test_build_book_tangles_override_text(tmp_path: Path) -> None:
    source = tmp_path / "src"
    write_chapter(source, "a.md", fence("python file=m.py", "old = 1"))
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.hydra]\noutputs = ["python"]\n',
        encoding="utf-8",
    )
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
        if item.name == "python":
            return item.rendered.files.data_for(Path("m.py"))
    return None
