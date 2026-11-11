""" Translation of basedpyright results, without a subprocess. """

from pathlib import Path

from lsprotocol import types

from hydra_tangler.serve.translate import (
    UnmappedLog,
    View,
    completion_from,
    hover_from,
    locations_from,
)
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
)


def test_results_map_through_the_source_map(tmp_path: Path) -> None:
    shadow = tmp_path / "shadow"
    source = tmp_path / "src"
    _ = shadow.mkdir()
    _ = source.mkdir()
    view = View(_map(), shadow, source, "inmemory://a.md", Path("a.md"))
    inside = (shadow / "m.py").resolve().as_uri()
    outside = (tmp_path / "stdlib.py").resolve().as_uri()
    hover = hover_from(view, Path("m.py"), _hover(1))
    defined = locations_from(view, _definitions(inside, outside))
    completed = completion_from(view, Path("m.py"), _completion(1))
    assert hover is not None
    assert hover.range is not None
    assert hover.range.start.line == 2
    assert defined is not None
    assert [item.uri for item in defined] == ["inmemory://a.md", outside]
    assert defined[0].range.start.line == 2
    assert defined[1].range.start.line == 4
    assert completed is not None
    assert completed.items[0].label == "greet"
    edit = completed.items[0].text_edit
    assert isinstance(edit, types.TextEdit)
    assert edit.range.start.line == 2


def test_an_unmapped_shadow_location_is_logged_once(tmp_path: Path) -> None:
    shadow = tmp_path / "shadow"
    _ = shadow.mkdir()
    view = View(
        _map(),
        shadow,
        tmp_path,
        "inmemory://a.md",
        Path("a.md"),
    )
    notes: list[str] = []
    misses = UnmappedLog(notes.append)
    inside = (shadow / "m.py").resolve().as_uri()
    outside = (tmp_path / "stdlib.py").resolve().as_uri()
    _ = locations_from(view, _definitions(inside, outside), misses)
    _ = locations_from(view, _definitions(inside, outside), misses)
    _ = completion_from(view, Path("m.py"), _completion(9), misses)
    _ = hover_from(view, Path("other.py"), _hover(4), misses)
    assert notes == [
        "unmapped-shadow-location: m.py",
        "unmapped-shadow-location: other.py",
    ]


def _map() -> SourceMap:
    return SourceMap(
        (
            SourceRecord(
                OutputSite(Path("m.py"), 2),
                MarkdownSite(Path("a.md"), 3),
            ),
        )
    )


def _hover(line: int) -> dict[str, object]:
    return {
        "contents": {"kind": "markdown", "value": "(function) greet"},
        "range": _range(line, 0, line, 5),
    }


def _definitions(inside: str, outside: str) -> list[object]:
    return [
        {"uri": inside, "range": _range(1, 0, 1, 5)},
        {"uri": inside, "range": _range(9, 0, 9, 1)},
        {"uri": outside, "range": _range(4, 1, 4, 2)},
    ]


def _completion(line: int) -> dict[str, object]:
    return {
        "isIncomplete": False,
        "items": [
            {
                "label": "greet",
                "kind": 3,
                "textEdit": {
                    "newText": "greet",
                    "range": _range(line, 0, line, 5),
                },
            }
        ],
    }


def _range(
    start: int,
    start_char: int,
    end: int,
    end_char: int,
) -> dict[str, object]:
    return {
        "start": {"line": start, "character": start_char},
        "end": {"line": end, "character": end_char},
    }
