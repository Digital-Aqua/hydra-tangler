""" Dead links and dead anchors. """

from pathlib import Path

from tests.books import write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.check.links import find_dead_links


def _codes(root: Path) -> tuple[str, ...]:
    return tuple(item.code for item in find_dead_links(load_book(root)))


def test_missing_file_is_a_dead_link(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", "See [gone](missing.md).\n")
    assert _codes(tmp_path) == ("dead-link",)


def test_missing_anchor_in_another_file(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", "See [there](b.md#missing).\n")
    write_chapter(tmp_path, "b.md", "# Present\n")
    found = find_dead_links(load_book(tmp_path))
    assert len(found) == 1
    assert found[0].code == "dead-anchor"
    assert found[0].path == Path("a.md")
    assert found[0].severity == "warning"


def test_missing_anchor_in_the_same_file(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        "# Title\n\n[nope](#missing) [ok](#title)\n",
    )
    found = find_dead_links(load_book(tmp_path))
    assert len(found) == 1
    assert found[0].code == "dead-anchor"
    assert found[0].message == "heading not found: #missing"


def test_external_links_are_ignored(tmp_path: Path) -> None:
    text = "\n".join(
        (
            "[web](https://example.com/a)",
            "[mail](mailto:a@b.c)",
            "[proto](//cdn.example/a)",
            "[root](/docs/index)",
            "",
        )
    )
    write_chapter(tmp_path, "a.md", text)
    assert _codes(tmp_path) == ()


def test_valid_links_are_silent(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "sub/a.md",
        "See [notes](../b.md#notes) and [pic](pic.png).\n",
    )
    write_chapter(tmp_path, "b.md", "# Notes\n")
    _ = (tmp_path / "sub").mkdir(exist_ok=True)
    _ = (tmp_path / "sub" / "pic.png").write_bytes(b"png")
    assert _codes(tmp_path) == ()


def test_renamed_file_is_a_dead_link(tmp_path: Path) -> None:
    write_chapter(tmp_path, "a.md", "See [notes](old.md).\n")
    write_chapter(tmp_path, "new.md", "# Notes\n")
    assert _codes(tmp_path) == ("dead-link",)
