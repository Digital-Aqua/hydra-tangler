""" Discover Markdown files and assemble them into a Book.

Documents are ordered alphabetically by relative path. Pass another
function to ``load_book`` to replace that order. An overrides map
supplies unsaved text in place of the file on disk. This module reads
the source tree and does not write an output directory, and it does
not choose which directory is the source.
"""

import os
import posixpath
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.model import Book, Diagnostic, Document
from hydra_tangler.parse import parse_document

Order = Callable[[Sequence[Path]], Sequence[Path]]

# Directory names never searched, wherever they sit in the source tree.
SKIPPED_DIRECTORIES = frozenset({"_build", "node_modules", "__pycache__"})


class SourceMissing(Exception):
    """ The source directory does not exist. """

    root: Path

    def __init__(self, root: Path) -> None:
        self.root = root
        super().__init__(f"source directory not found: {root}")


class UnreadableSource(Exception):
    """ A Markdown or tangled file could not be read as text. """

    path: Path

    def __init__(self, path: Path, reason: str) -> None:
        self.path = path
        super().__init__(f"cannot read {path}: {reason}")


@dataclass(frozen=True)
class _Chosen:
    """ Override text that belongs in the book, and the entries dropped. """

    text: dict[Path, str]
    diagnostics: tuple[Diagnostic, ...]


def alphabetical(paths: Sequence[Path]) -> tuple[Path, ...]:
    """ Sort paths by their POSIX spelling. """
    return tuple(sorted(paths, key=lambda path: path.as_posix()))


def load_book(
    root: Path,
    order: Order = alphabetical,
    *,
    overrides: Mapping[Path, str] | None = None,
    target: Path | None = None,
) -> Book:
    """ Read every ``*.md`` file under ``root`` and parse it.

    ``order`` receives paths relative to ``root`` and decides the
    document sequence. Hidden directories, ``SKIPPED_DIRECTORIES``,
    and ``target`` when it is a directory inside ``root`` are not
    searched. ``overrides`` maps a relative path to text that replaces
    the file on disk. A Markdown path that is not on disk is still
    included, so an unsaved buffer can join the book.
    """
    if not root.is_dir():
        raise SourceMissing(root)
    blocked = _relative_target(root, target)
    chosen = _normalized(overrides, blocked)
    documents: list[Document] = []
    diagnostics: list[Diagnostic] = list(chosen.diagnostics)
    texts: dict[Path, str] = {}
    for relative in order(_markdown_paths(root, chosen.text, blocked)):
        body = _text(root, relative, chosen.text)
        texts[relative] = body
        parsed = parse_document(body, relative)
        documents.append(parsed.document)
        diagnostics.extend(parsed.diagnostics)
    return Book(root, tuple(documents), tuple(diagnostics), texts)


def _normalized(
    overrides: Mapping[Path, str] | None,
    blocked: Path | None,
) -> _Chosen:
    if overrides is None:
        return _Chosen({}, ())
    chosen: dict[Path, str] = {}
    dropped: list[Diagnostic] = []
    for relative, text in overrides.items():
        path = _override_path(relative, blocked)
        if path is None:
            dropped.append(_ignored(relative, blocked))
            continue
        chosen[path] = text
    return _Chosen(chosen, tuple(dropped))


def _ignored(relative: Path, blocked: Path | None) -> Diagnostic:
    return Diagnostic(
        relative,
        1,
        "warning",
        "ignored-override",
        _ignore_reason(relative, blocked),
    )


def _ignore_reason(relative: Path, blocked: Path | None) -> str:
    if relative.is_absolute():
        return "override path is absolute"
    normal = posixpath.normpath(relative.as_posix())
    if normal in (".", "..") or normal.startswith("../"):
        return "override path escapes the book root"
    path = Path(normal)
    if path.suffix != ".md":
        return "override path is not a Markdown file"
    if _is_hidden(path) or _skipped(path):
        return "override path is hidden or in a skipped directory"
    if _under_blocked(path, blocked):
        return "override path is inside the build directory"
    return "override path was ignored"


def _skipped(relative: Path) -> bool:
    return any(part in SKIPPED_DIRECTORIES for part in relative.parts)


def _override_path(relative: Path, blocked: Path | None) -> Path | None:
    if relative.is_absolute():
        return None
    normal = posixpath.normpath(relative.as_posix())
    if normal in (".", "..") or normal.startswith("../"):
        return None
    path = Path(normal)
    if path.suffix != ".md" or _excluded(path, blocked):
        return None
    return path


def _markdown_paths(
    root: Path,
    overrides: Mapping[Path, str],
    blocked: Path | None,
) -> tuple[Path, ...]:
    found = set(_markdown_files(root, blocked))
    found.update(overrides)
    return tuple(found)


def _text(root: Path, relative: Path, overrides: Mapping[Path, str]) -> str:
    if relative in overrides:
        return overrides[relative]
    return _read_source(root / relative)


def _read_source(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        reason = err.strerror or str(err)
        raise UnreadableSource(path, reason) from err
    except UnicodeDecodeError as err:
        raise UnreadableSource(path, str(err)) from err


def _markdown_files(root: Path, blocked: Path | None) -> tuple[Path, ...]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        _prune(root, directory, dirnames, blocked)
        found.extend(_markdown_names(root, directory, filenames))
    return tuple(found)


def _prune(
    root: Path,
    directory: str,
    dirnames: list[str],
    blocked: Path | None,
) -> None:
    kept: list[str] = []
    for name in dirnames:
        if _skip_directory(root, Path(directory) / name, blocked):
            continue
        kept.append(name)
    dirnames[:] = kept


def _markdown_names(
    root: Path,
    directory: str,
    filenames: list[str],
) -> tuple[Path, ...]:
    found: list[Path] = []
    for name in filenames:
        if not name.endswith(".md") or name.startswith("."):
            continue
        path = Path(directory) / name
        if not path.is_file():
            continue
        found.append(Path(path.relative_to(root).as_posix()))
    return tuple(found)


def _relative_target(root: Path, target: Path | None) -> Path | None:
    """ ``target`` relative to ``root``, when it is strictly inside. """
    if target is None:
        return None
    try:
        relative = target.resolve().relative_to(root.resolve())
    except ValueError:
        return None
    if not relative.parts:
        return None
    return Path(relative.as_posix())


def _excluded(relative: Path, blocked: Path | None) -> bool:
    if _is_hidden(relative):
        return True
    if _skipped(relative):
        return True
    return _under_blocked(relative, blocked)


def _under_blocked(relative: Path, blocked: Path | None) -> bool:
    if blocked is None:
        return False
    return relative.parts[: len(blocked.parts)] == blocked.parts


def _skip_directory(root: Path, path: Path, blocked: Path | None) -> bool:
    name = path.name
    if name.startswith(".") or name in SKIPPED_DIRECTORIES:
        return True
    if blocked is None:
        return False
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return Path(relative.as_posix()) == blocked


def _is_hidden(relative: Path) -> bool:
    return any(part.startswith(".") for part in relative.parts)
