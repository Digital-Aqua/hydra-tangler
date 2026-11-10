""" The watch loop, driven by a stub change stream. """

from pathlib import Path

from hydra_tangler.watch import watch_markdown


def test_markdown_changes_call_back(tmp_path: Path) -> None:
    calls: list[Path] = []
    notes = tmp_path / "notes.md"
    built = tmp_path / "out" / "page.md"
    other = tmp_path / "out" / "m.py"

    def on_change() -> None:
        calls.append(notes)

    watch_markdown(
        tmp_path,
        on_change,
        ignore=(tmp_path / "out",),
        batches=((notes,), (built, other), (tmp_path / "more.md",)),
    )
    assert calls == [notes, notes]


def test_an_ignored_directory_stays_quiet(tmp_path: Path) -> None:
    calls: list[int] = []
    watch_markdown(
        tmp_path,
        lambda: calls.append(1),
        ignore=(tmp_path / "out",),
        batches=((tmp_path / "out" / "readme.md",),),
    )
    assert calls == []
