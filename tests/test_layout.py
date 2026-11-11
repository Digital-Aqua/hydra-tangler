""" One target directory, mounts, collisions, and sourcemap.json. """

import json
import os
from pathlib import Path
from typing import cast

from tests.books import fence, write_chapter

from hydra_tangler.model import Diagnostic
from hydra_tangler.mounting import SOURCEMAP_PATH, merged_source_map
from hydra_tangler.pipeline import BuildResult, build_book, write_rendered
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
    load_source_map,
    to_json,
)


def test_mounted_write_is_one_directory(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=pkg/m.py", "x = 1"))
    result = build_book(tmp_path)
    target = tmp_path / "out"
    written = write_rendered(result, tmp_path, target)
    assert written == target
    assert (target / "pkg" / "m.py").is_file()
    assert (target / "docs" / "c.html").is_file()
    assert (target / "sourcemap.json").is_file()
    assert not (target / "files").exists()
    assert not (target / "htmldocs").exists()
    manifests = list(target.rglob(".hydra-manifest.json"))
    assert manifests == [target / ".hydra-manifest.json"]


def test_docs_path_collides_when_htmldocs_is_selected(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=docs/x.txt", "x = 1"))
    result = build_book(tmp_path)
    item = _collision(result)
    assert item.path == Path("c.md")
    assert "docs/x.txt" in item.message
    files_only = build_book(tmp_path, outputs=("files",))
    assert files_only.diagnostics == ()


def test_reserved_sourcemap_name_is_an_error(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "c.md",
        fence("python file=sourcemap.json", "x = 1"),
    )
    result = build_book(tmp_path, outputs=("files",))
    item = _collision(result)
    assert item.path == Path("c.md")
    assert item.message.startswith(SOURCEMAP_PATH.as_posix())


def test_book_source_map_round_trips(tmp_path: Path) -> None:
    write_chapter(
        tmp_path,
        "a.md",
        fence("python file=pkg/m.py", "a = 1", "a2 = 2"),
    )
    write_chapter(
        tmp_path,
        "b.md",
        fence("python file=pkg/m.py", "b = 1", "b2 = 2"),
    )
    result = build_book(tmp_path, outputs=("files", "htmldocs"))
    source_map = merged_source_map(result.outputs)
    origins = {
        record.markdown.path
        for record in source_map.records
        if record.output.path == Path("pkg/m.py")
    }
    assert origins == {Path("a.md"), Path("b.md")}
    assert load_source_map(to_json(source_map)) == _canonical(source_map)


def test_run_length_segments_round_trip() -> None:
    records = [
        _record("pkg/m.py", line, "a.md", line)
        for line in (1, 2, 3)
    ]
    records.append(_record("pkg/m.py", 5, "b.md", 9))
    records.append(_record("docs/ch/a.html", 4, "ch/a.md", 8))
    source_map = SourceMap(tuple(records))
    text = to_json(source_map)
    assert text == to_json(source_map)
    payload = _object(cast(object, json.loads(text)))
    segments = _object(_files(payload)["pkg/m.py"])["segments"]
    assert segments == [
        {"count": 3, "md_start": 1, "out_start": 1, "source": 0},
        {"count": 1, "md_start": 9, "out_start": 5, "source": 1},
    ]
    assert "docs/ch/a.html" in _files(payload)
    assert load_source_map(text) == _canonical(source_map)


def test_unchanged_sourcemap_is_not_rewritten(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=m.py", "x = 1"))
    result = build_book(tmp_path, outputs=("files",))
    target = tmp_path / "out"
    _ = write_rendered(result, tmp_path, target)
    path = target / "sourcemap.json"
    stamp = 1_700_000_000
    os.utime(path, (stamp, stamp))
    _ = write_rendered(result, tmp_path, target)
    assert path.stat().st_mtime == stamp


def _collision(result: BuildResult) -> Diagnostic:
    found = [
        item
        for item in result.diagnostics
        if item.code == "output-collision"
    ]
    assert len(found) == 1
    return found[0]


def _record(
    output: str,
    output_line: int,
    markdown: str,
    markdown_line: int,
) -> SourceRecord:
    return SourceRecord(
        OutputSite(Path(output), output_line),
        MarkdownSite(Path(markdown), markdown_line),
    )


def _canonical(source_map: SourceMap) -> SourceMap:
    ordered = sorted(
        source_map.records,
        key=lambda record: (
            record.output.path.as_posix(),
            record.output.line,
        ),
    )
    return SourceMap(tuple(ordered))


def _object(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _files(payload: dict[str, object]) -> dict[str, object]:
    return _object(payload["files"])
