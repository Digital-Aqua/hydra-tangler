""" Position translation between Markdown and tangled Python. """

from pathlib import Path

from hydra_tangler.serve.positions import (
    FilePosition,
    FileRange,
    markdown_range,
    output_position,
)
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
)


def test_python_line_maps_back_to_markdown() -> None:
    source_map = _map()
    found = output_position(source_map, Path("a.md"), 1, 4)
    span = markdown_range(
        source_map,
        FileRange(Path("m.py"), 1, 0, 1, 3),
    )
    assert found == FilePosition(Path("m.py"), 1, 4)
    assert span == FileRange(Path("a.md"), 1, 0, 1, 3)


def test_a_range_that_leaves_the_fence_is_pinned() -> None:
    span = markdown_range(_map(), FileRange(Path("m.py"), 1, 0, 5, 1))
    assert span == FileRange(Path("a.md"), 1, 0, 1, 10_000)


def test_prose_has_no_python_position() -> None:
    assert output_position(_map(), Path("a.md"), 4, 0) is None


def _map() -> SourceMap:
    return SourceMap(
        (
            SourceRecord(
                OutputSite(Path("m.py"), 1),
                MarkdownSite(Path("a.md"), 1),
            ),
            SourceRecord(
                OutputSite(Path("m.py"), 2),
                MarkdownSite(Path("a.md"), 2),
            ),
        )
    )
