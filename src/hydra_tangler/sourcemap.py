""" Map output lines to the Markdown lines that produced them.

A map is pure data built by an output. The pipeline merges maps and
may write one ``sourcemap.json``; this module serializes and loads
that file and does not choose a directory or touch the disk itself.
Look up an output line to find the Markdown site, or a Markdown line
to find the output sites it produced.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast


@dataclass(frozen=True)
class MarkdownSite:
    """ A line in a source document. """

    path: Path
    line: int


@dataclass(frozen=True)
class OutputSite:
    """ A line in a tangled file. """

    path: Path
    line: int


@dataclass(frozen=True)
class SourceRecord:
    """ One output line and the Markdown line it came from. """

    output: OutputSite
    markdown: MarkdownSite


@dataclass(frozen=True)
class SourceMap:
    """ The records for every file in one output. """

    records: tuple[SourceRecord, ...] = ()

    def markdown_at(self, path: Path, line: int) -> MarkdownSite | None:
        """ Return the Markdown site that produced ``path:line``. """
        for record in self.records:
            if record.output.path == path and record.output.line == line:
                return record.markdown
        return None

    def output_at(self, path: Path, line: int) -> tuple[OutputSite, ...]:
        """ Return output sites produced by this Markdown line. """
        return tuple(
            record.output
            for record in self.records
            if record.markdown.path == path and record.markdown.line == line
        )


def to_json(source_map: SourceMap) -> str:
    """ Serialize ``source_map`` with sorted paths and run-length segments.

    Consecutive output lines that map to consecutive lines of the same
    Markdown file become one segment. Key order is sorted so an
    unchanged map compares equal as text.
    """
    grouped = _by_output(source_map)
    files: dict[str, object] = {}
    for path in sorted(grouped):
        files[path] = _file_entry(grouped[path])
    payload: dict[str, object] = {"version": 1, "files": files}
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def load_source_map(text: str) -> SourceMap:
    """ Rebuild a source map from text produced by ``to_json``.

    Records come back sorted by output path, then output line.
    """
    payload = _as_dict(_decode(text))
    if payload is None or payload.get("version") != 1:
        raise ValueError("source map must be version 1")
    files = _as_dict(payload.get("files"))
    if files is None:
        raise ValueError("source map has no files object")
    records: list[SourceRecord] = []
    for path in sorted(files):
        records.extend(_file_records(path, files[path]))
    return SourceMap(tuple(records))


def _by_output(source_map: SourceMap) -> dict[str, list[SourceRecord]]:
    grouped: dict[str, list[SourceRecord]] = {}
    for record in source_map.records:
        key = record.output.path.as_posix()
        grouped.setdefault(key, []).append(record)
    return grouped


def _file_entry(records: Sequence[SourceRecord]) -> dict[str, object]:
    sources, segments = _compact(records)
    return {"sources": sources, "segments": segments}


def _compact(
    records: Sequence[SourceRecord],
) -> tuple[list[str], list[dict[str, int]]]:
    sources: list[str] = []
    segments: list[dict[str, int]] = []
    ordered = sorted(records, key=lambda record: record.output.line)
    for record in ordered:
        index = _source_index(sources, record.markdown.path.as_posix())
        if _extends(segments, index, record):
            segments[-1]["count"] += 1
            continue
        segments.append(_segment(record, index))
    return sources, segments


def _source_index(sources: list[str], path: str) -> int:
    if path not in sources:
        sources.append(path)
    return sources.index(path)


def _extends(
    segments: Sequence[dict[str, int]],
    index: int,
    record: SourceRecord,
) -> bool:
    if not segments or segments[-1]["source"] != index:
        return False
    last = segments[-1]
    previous_out = last["out_start"] + last["count"]
    previous_md = last["md_start"] + last["count"]
    return (
        record.output.line == previous_out
        and record.markdown.line == previous_md
    )


def _segment(record: SourceRecord, index: int) -> dict[str, int]:
    return {
        "out_start": record.output.line,
        "count": 1,
        "source": index,
        "md_start": record.markdown.line,
    }


def _file_records(path: str, raw: object) -> tuple[SourceRecord, ...]:
    entry = _as_dict(raw)
    if entry is None:
        raise ValueError(f"bad source map entry for {path}")
    sources = _strings(entry.get("sources"), path)
    segments = _as_list(entry.get("segments"))
    if segments is None:
        raise ValueError(f"bad segments for {path}")
    records: list[SourceRecord] = []
    for item in segments:
        records.extend(_expand(path, sources, item))
    return tuple(records)


def _expand(
    path: str,
    sources: Sequence[str],
    raw: object,
) -> tuple[SourceRecord, ...]:
    segment = _as_dict(raw)
    if segment is None:
        raise ValueError(f"bad segment in {path}")
    start = _integer(segment.get("out_start"), path)
    count = _integer(segment.get("count"), path)
    source = _integer(segment.get("source"), path)
    markdown = _integer(segment.get("md_start"), path)
    if source < 0 or source >= len(sources):
        raise ValueError(f"bad source index in {path}")
    origin = Path(sources[source])
    return tuple(
        SourceRecord(
            OutputSite(Path(path), start + offset),
            MarkdownSite(origin, markdown + offset),
        )
        for offset in range(count)
    )


def _strings(raw: object, path: str) -> tuple[str, ...]:
    items = _as_list(raw)
    if items is None or not all(isinstance(item, str) for item in items):
        raise ValueError(f"bad sources for {path}")
    return tuple(item for item in items if isinstance(item, str))


def _integer(raw: object, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ValueError(f"bad segment number in {path}")
    return raw


def _decode(text: str) -> object:
    try:
        return cast(object, json.loads(text))
    except json.JSONDecodeError as err:
        raise ValueError("source map is not JSON") from err


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None
