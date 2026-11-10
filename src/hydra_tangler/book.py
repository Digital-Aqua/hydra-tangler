""" Discover Markdown files and assemble them into a Book.

Documents are ordered alphabetically by relative path. Pass another
function to ``load_book`` to replace that order. An overrides map
supplies unsaved text in place of the file on disk. This module reads
the source tree and does not write an output directory.
"""

import posixpath
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from hydra_tangler.model import Book, Diagnostic, Document
from hydra_tangler.parse import parse_document

Order = Callable[[Sequence[Path]], Sequence[Path]]

_SOURCE_CANDIDATES = ("src", "source")


class SourceMissing(Exception):
    """ The source directory does not exist. """

    root: Path

    def __init__(self, root: Path) -> None:
        self.root = root
        super().__init__(f"source directory not found: {root}")


def default_source(cwd: Path) -> Path:
    """ Return ``./src``, else ``./source``, else ``./``. """
    for name in _SOURCE_CANDIDATES:
        candidate = cwd / name
        if candidate.is_dir():
            return candidate
    return cwd


def alphabetical(paths: Sequence[Path]) -> tuple[Path, ...]:
    """ Sort paths by their POSIX spelling. """
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def load_book(
    root: Path,
    order: Order = alphabetical,
    *,
    overrides: Mapping[Path, str] | None = None,
) -> Book:
    """ Read every ``*.md`` file under ``root`` and parse it.

    ``order`` receives paths relative to ``root`` and decides the
    document sequence. Hidden directories (names starting with ``.``)
    are not searched. ``overrides`` maps a relative path to text that
    replaces the file on disk. A Markdown path that is not on disk is
    still included, so an unsaved buffer can join the book.
    """
    if not root.is_dir():
        raise SourceMissing(root)
    chosen = _normalized(overrides)
    documents: list[Document] = []
    diagnostics: list[Diagnostic] = []
    for relative in order(_markdown_paths(root, chosen)):
        parsed = parse_document(_text(root, relative, chosen), relative)
        documents.append(parsed.document)
        diagnostics.extend(parsed.diagnostics)
    return Book(root, tuple(documents), tuple(diagnostics))


def _normalized(overrides: Mapping[Path, str] | None) -> dict[Path, str]:
    if overrides is None:
        return {}
    chosen: dict[Path, str] = {}
    for relative, text in overrides.items():
        path = _override_path(relative)
        if path is not None:
            chosen[path] = text
    return chosen


def _override_path(relative: Path) -> Path | None:
    if relative.is_absolute():
        return None
    normal = posixpath.normpath(relative.as_posix())
    if normal in (".", "..") or normal.startswith("../"):
        return None
    path = Path(normal)
    if path.suffix != ".md" or _is_hidden(path):
        return None
    return path


def _markdown_paths(
    root: Path,
    overrides: Mapping[Path, str],
) -> tuple[Path, ...]:
    found = set(_markdown_files(root))
    found.update(overrides)
    return tuple(found)


def _text(root: Path, relative: Path, overrides: Mapping[Path, str]) -> str:
    if relative in overrides:
        return overrides[relative]
    return (root / relative).read_text(encoding="utf-8")


def _markdown_files(root: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for path in root.rglob("*.md"):
        if not path.is_file():
            continue
        relative = Path(path.relative_to(root).as_posix())
        if _is_hidden(relative):
            continue
        found.append(relative)
    return tuple(found)


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)
