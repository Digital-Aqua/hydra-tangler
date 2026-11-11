""" Turn basedpyright results into Markdown locations.

Ranges inside the shadow tree are mapped through the source map.
A location outside that tree is returned unchanged. A location in
the shadow that the map does not know is dropped, and reported once
per output path when the caller passes an ``UnmappedLog``. A miss
that is not inside the shadow stays silent. This module does not
speak to a process.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from lsprotocol import types
from pygls.uris import to_fs_path

from hydra_tangler.serve.positions import FileRange, markdown_range
from hydra_tangler.sourcemap import SourceMap


class UnmappedLog:
    """ Report each unmapped shadow path once. """

    def __init__(self, log: Callable[[str], None]) -> None:
        self._log: Callable[[str], None] = log
        self._seen: set[Path] = set()
        self._lock: threading.Lock = threading.Lock()

    def note(self, path: Path) -> None:
        """ Log ``unmapped-shadow-location`` the first time for ``path``. """
        with self._lock:
            if path in self._seen:
                return
            self._seen.add(path)
        self._log(f"unmapped-shadow-location: {path.as_posix()}")


@dataclass(frozen=True)
class View:
    """ The book a result is being translated for. """

    source_map: SourceMap
    shadow: Path
    source: Path
    request_uri: str
    request_path: Path


def hover_from(
    view: View,
    output: Path,
    payload: object,
    misses: UnmappedLog | None = None,
) -> types.Hover | None:
    """ Build a hover for ``output``, or None when there is no text. """
    record = _as_dict(payload)
    if record is None:
        return None
    text = _contents(record.get("contents"))
    if not text:
        return None
    return types.Hover(
        contents=types.MarkupContent(
            kind=types.MarkupKind.Markdown,
            value=text,
        ),
        range=_hover_range(view, output, record.get("range"), misses),
    )


def locations_from(
    view: View,
    payload: object,
    misses: UnmappedLog | None = None,
) -> list[types.Location] | None:
    """ Map a definition result onto Markdown locations. """
    records = _records(payload)
    if records is None:
        return None
    found: list[types.Location] = []
    for record in records:
        location = _location(view, record, misses)
        if location is not None:
            found.append(location)
    if not found:
        return None
    return found


def completion_from(
    view: View,
    output: Path,
    payload: object,
    misses: UnmappedLog | None = None,
) -> types.CompletionList | None:
    """ Map completion edits onto the Markdown document. """
    items = _items(payload)
    if items is None:
        return None
    built = [
        _item(view, output, record, misses) for record in items.records
    ]
    return types.CompletionList(
        is_incomplete=items.incomplete,
        items=[item for item in built if item is not None],
    )


@dataclass(frozen=True)
class _Items:
    records: tuple[dict[str, object], ...]
    incomplete: bool


@dataclass(frozen=True)
class _Point:
    line: int
    character: int


@dataclass(frozen=True)
class _Span:
    start: _Point
    end: _Point


@dataclass(frozen=True)
class _Place:
    inside: bool
    relative: Path | None


def _hover_range(
    view: View,
    output: Path,
    raw: object,
    misses: UnmappedLog | None,
) -> types.Range | None:
    span = _span(raw)
    if span is None:
        return None
    mapped = markdown_range(view.source_map, _output_range(output, span))
    if mapped is None:
        _note(misses, output)
        return None
    if mapped.path != view.request_path:
        return None
    return _lsp_range(mapped)


def _location(
    view: View,
    record: dict[str, object],
    misses: UnmappedLog | None,
) -> types.Location | None:
    uri = _uri_field(record)
    span = _span(record.get("targetSelectionRange"))
    if span is None:
        span = _span(record.get("range"))
    if uri is None or span is None:
        return None
    place = _place(view.shadow, uri)
    if not place.inside:
        return types.Location(uri=uri, range=_raw_range(span))
    if place.relative is None:
        return None
    mapped = markdown_range(
        view.source_map,
        _output_range(place.relative, span),
    )
    if mapped is None:
        _note(misses, place.relative)
        return None
    return types.Location(
        uri=_document_uri(view, mapped.path),
        range=_lsp_range(mapped),
    )


def _item(
    view: View,
    output: Path,
    record: dict[str, object],
    misses: UnmappedLog | None,
) -> types.CompletionItem | None:
    label = record.get("label")
    if not isinstance(label, str) or not label:
        return None
    detail = record.get("detail")
    insert = record.get("insertText")
    return types.CompletionItem(
        label=label,
        kind=_kind(record.get("kind")),
        detail=detail if isinstance(detail, str) else None,
        insert_text=insert if isinstance(insert, str) else None,
        text_edit=_text_edit(view, output, record.get("textEdit"), misses),
    )


def _text_edit(
    view: View,
    output: Path,
    raw: object,
    misses: UnmappedLog | None,
) -> types.TextEdit | None:
    record = _as_dict(raw)
    if record is None:
        return None
    new_text = record.get("newText")
    span = _edit_span(record)
    if not isinstance(new_text, str) or span is None:
        return None
    mapped = markdown_range(view.source_map, _output_range(output, span))
    if mapped is None:
        _note(misses, output)
        return None
    if mapped.path != view.request_path:
        return None
    return types.TextEdit(range=_lsp_range(mapped), new_text=new_text)


def _note(misses: UnmappedLog | None, path: Path) -> None:
    if misses is not None:
        misses.note(path)


def _edit_span(record: dict[str, object]) -> _Span | None:
    span = _span(record.get("range"))
    if span is not None:
        return span
    return _span(record.get("insert"))


def _items(payload: object) -> _Items | None:
    if isinstance(payload, list):
        return _Items(_dicts(cast(list[object], payload)), False)
    record = _as_dict(payload)
    if record is None:
        return None
    raw = record.get("items")
    if not isinstance(raw, list):
        return None
    incomplete = record.get("isIncomplete") is True
    return _Items(_dicts(cast(list[object], raw)), incomplete)


def _records(payload: object) -> tuple[dict[str, object], ...] | None:
    record = _as_dict(payload)
    if record is not None:
        return (record,)
    if isinstance(payload, list):
        return _dicts(cast(list[object], payload))
    return None


def _dicts(payload: list[object]) -> tuple[dict[str, object], ...]:
    found: list[dict[str, object]] = []
    for item in payload:
        record = _as_dict(item)
        if record is not None:
            found.append(record)
    return tuple(found)


def _contents(value: object) -> str:
    if isinstance(value, str):
        return value
    record = _as_dict(value)
    if record is not None:
        return _one_content(record)
    if isinstance(value, list):
        return _joined(cast(list[object], value))
    return ""


def _joined(items: list[object]) -> str:
    parts = [_contents(item) for item in items]
    return "\n\n".join(part for part in parts if part)


def _one_content(record: dict[str, object]) -> str:
    value = record.get("value")
    if isinstance(value, str):
        return value
    return ""


def _kind(value: object) -> types.CompletionItemKind | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    try:
        return types.CompletionItemKind(value)
    except ValueError:
        return None


def _place(shadow: Path, uri: str) -> _Place:
    raw = to_fs_path(uri)
    if not raw:
        return _Place(False, None)
    try:
        relative = Path(raw).resolve().relative_to(shadow.resolve())
    except ValueError:
        return _Place(False, None)
    return _Place(True, Path(relative.as_posix()))


def _document_uri(view: View, path: Path) -> str:
    if path == view.request_path:
        return view.request_uri
    return (view.source / path).resolve().as_uri()


def _output_range(path: Path, span: _Span) -> FileRange:
    return FileRange(
        path,
        span.start.line,
        span.start.character,
        span.end.line,
        span.end.character,
    )


def _lsp_range(span: FileRange) -> types.Range:
    start = _position(span.start_line, span.start_character)
    end = _position(span.end_line, span.end_character)
    return types.Range(start=start, end=end)


def _raw_range(span: _Span) -> types.Range:
    start = _position(span.start.line, span.start.character)
    end = _position(span.end.line, span.end.character)
    return types.Range(start=start, end=end)


def _position(line: int, character: int) -> types.Position:
    return types.Position(line=line, character=character)


def _uri_field(record: dict[str, object]) -> str | None:
    for key in ("uri", "targetUri"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _span(value: object) -> _Span | None:
    record = _as_dict(value)
    if record is None:
        return None
    start = _point(record.get("start"))
    end = _point(record.get("end"))
    if start is None or end is None:
        return None
    return _Span(start, end)


def _point(value: object) -> _Point | None:
    record = _as_dict(value)
    if record is None:
        return None
    line = record.get("line")
    character = record.get("character")
    if isinstance(line, bool) or isinstance(character, bool):
        return None
    if not isinstance(line, int) or not isinstance(character, int):
        return None
    return _Point(line, character)


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None
