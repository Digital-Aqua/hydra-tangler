""" In-memory text of Markdown files the editor has open.

Paths are relative to the book's source directory. Closed files drop
out of the map so the next rebuild reads the disk again. This module
does not parse Markdown or talk to the client.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from pygls.uris import to_fs_path


@dataclass(frozen=True)
class OpenBuffer:
    """ One open Markdown document. ``uri`` is the client's URI. """

    uri: str
    text: str


class DocumentStore:
    """ Open buffers keyed by a path relative to the source directory. """

    def __init__(self) -> None:
        self._open: dict[Path, OpenBuffer] = {}

    def remember(self, source: Path, uri: str, text: str) -> bool:
        """ Store ``text`` when ``uri`` is Markdown under ``source``. """
        relative = markdown_relative(source, uri)
        if relative is None:
            return False
        self._open[relative] = OpenBuffer(uri, text)
        return True

    def forget(self, source: Path, uri: str) -> bool:
        """ Drop a buffer. Return whether it was open. """
        relative = markdown_relative(source, uri)
        if relative is None:
            return False
        return self._open.pop(relative, None) is not None

    def overrides(self) -> Mapping[Path, str]:
        """ A snapshot of relative path to buffer text. """
        return MappingProxyType(
            {path: item.text for path, item in self._open.items()}
        )

    def uris(self) -> Mapping[Path, str]:
        """ A snapshot of relative path to the client's URI. """
        return MappingProxyType(
            {path: item.uri for path, item in self._open.items()}
        )


def markdown_relative(source: Path, uri: str) -> Path | None:
    """ Return ``uri`` relative to ``source`` when it is a Markdown file. """
    raw = to_fs_path(uri)
    if raw is None:
        return None
    return _relative(source, Path(raw))


def _relative(source: Path, path: Path) -> Path | None:
    if path.suffix != ".md":
        return None
    try:
        relative = path.resolve().relative_to(source.resolve())
    except ValueError:
        return None
    posix = Path(relative.as_posix())
    if _hidden(posix):
        return None
    return posix


def _hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)
