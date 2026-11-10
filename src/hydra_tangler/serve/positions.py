""" Translate positions between Markdown and tangled Python.

A column is copied through unchanged. That matches the language
server protocol when the line is ASCII; a line with characters
outside the basic multilingual plane can disagree by a column.
This module does not start a process or speak JSON-RPC.
"""

from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.sourcemap import SourceMap

# A range that leaves one fence is pinned to the rest of the start
# line, the same way a prose gap cannot be edited as one Python range.
_REST_OF_LINE = 10_000


@dataclass(frozen=True)
class FilePosition:
    """ A 0-based position in a file relative to its tree. """

    path: Path
    line: int
    character: int


@dataclass(frozen=True)
class FileRange:
    """ A 0-based range in a file relative to its tree. """

    path: Path
    start_line: int
    start_character: int
    end_line: int
    end_character: int


def output_position(
    source_map: SourceMap,
    markdown: Path,
    line: int,
    character: int,
) -> FilePosition | None:
    """ Map a Markdown position onto the first Python line it produced. """
    sites = source_map.output_at(markdown, line + 1)
    for site in sites:
        if site.path.suffix == ".py":
            return FilePosition(site.path, site.line - 1, character)
    return None


def markdown_range(
    source_map: SourceMap,
    output: FileRange,
) -> FileRange | None:
    """ Map a Python range back onto Markdown.

    Both ends are kept when they stay in one file and the line gap is
    the same. Otherwise the range is the start line only.
    """
    start = _markdown_at(
        source_map,
        output.path,
        output.start_line,
        output.start_character,
    )
    if start is None:
        return None
    end = _markdown_at(
        source_map,
        output.path,
        output.end_line,
        output.end_character,
    )
    if end is not None and _same_gap(output, start, end):
        return _between(start, end)
    return _pinned(start)


def _between(start: FilePosition, end: FilePosition) -> FileRange:
    return FileRange(
        start.path,
        start.line,
        start.character,
        end.line,
        end.character,
    )


def _pinned(start: FilePosition) -> FileRange:
    return FileRange(
        start.path,
        start.line,
        start.character,
        start.line,
        _REST_OF_LINE,
    )


def _markdown_at(
    source_map: SourceMap,
    path: Path,
    line: int,
    character: int,
) -> FilePosition | None:
    site = source_map.markdown_at(path, line + 1)
    if site is None:
        return None
    return FilePosition(site.path, site.line - 1, character)


def _same_gap(
    output: FileRange,
    start: FilePosition,
    end: FilePosition,
) -> bool:
    if end.path != start.path:
        return False
    return end.line - start.line == output.end_line - output.start_line
