""" Write a FileSet into a directory.

Unchanged files are left untouched, so their modification time stays
put and a watcher does not wake itself. Files this writer created on
a previous run, and that the new FileSet no longer contains, are
removed. The previous run is recorded in ``.hydra-manifest.json`` in
the output directory. No other module writes that directory.
"""

import json
from pathlib import Path
from typing import cast

from hydra_tangler.model import FileSet, OutputFile

MANIFEST_NAME = ".hydra-manifest.json"


class WriterError(Exception):
    """ The file set cannot be written into the output directory. """


def write_files(file_set: FileSet, directory: Path) -> None:
    """ Create ``directory`` and bring it in line with ``file_set``. """
    directory.mkdir(parents=True, exist_ok=True)
    previous = _read_manifest(directory)
    written = {item.path.as_posix() for item in file_set.files}
    for item in file_set.files:
        _place(directory, item)
    for relative in previous:
        if relative in written or relative == MANIFEST_NAME:
            continue
        _remove(directory, relative)
    _write_manifest(directory, written)


def _place(directory: Path, item: OutputFile) -> None:
    destination = _within(directory, item.path)
    if destination.exists() and not destination.is_file():
        raise WriterError(f"{item.path.as_posix()} is not a file")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() == item.data:
        return
    _ = destination.write_bytes(item.data)


def _remove(directory: Path, relative: str) -> None:
    destination = _within(directory, Path(relative))
    if destination.is_file():
        destination.unlink()
    _remove_empty_parents(destination.parent, directory)


def _remove_empty_parents(start: Path, root: Path) -> None:
    current = start
    while current != root and _inside(current, root):
        if not current.is_dir() or any(current.iterdir()):
            return
        current.rmdir()
        current = current.parent


def _read_manifest(directory: Path) -> tuple[str, ...]:
    path = directory / MANIFEST_NAME
    if not path.is_file():
        return ()
    try:
        decoded: object = _decode_manifest(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise WriterError(f"cannot read {path}") from err
    payload = _as_dict(decoded)
    if payload is None:
        raise WriterError(f"cannot read {path}")
    return tuple(_manifest_paths(path, payload.get("files")))


def _write_manifest(directory: Path, paths: set[str]) -> None:
    payload = json.dumps({"files": sorted(paths)}, indent=2) + "\n"
    _place(
        directory,
        OutputFile(Path(MANIFEST_NAME), payload.encode("utf-8")),
    )


def _manifest_paths(path: Path, raw: object) -> list[str]:
    items = _as_list(raw)
    if items is None:
        raise WriterError(f"cannot read {path}")
    paths: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise WriterError(f"cannot read {path}")
        paths.append(item)
    return paths


def _within(directory: Path, relative: Path) -> Path:
    if relative.is_absolute() or ".." in relative.parts:
        raise WriterError(f"refusing to write {relative.as_posix()}")
    destination = directory.joinpath(relative)
    if not _inside(destination, directory):
        raise WriterError(f"refusing to write {relative.as_posix()}")
    return destination


def _inside(path: Path, root: Path) -> bool:
    try:
        _ = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def _decode_manifest(text: str) -> object:
    return cast(object, json.loads(text))


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None
