""" Plain data shared by every layer.

These types carry parsed documents, diagnostics, and the bytes an
output wants written. They do not read files, write files, or decide
what a fence means. ``vet_output_path`` is the containment rule every
layer uses; it does not look at the filesystem or follow symlinks.
"""

import posixpath
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]


def _empty_texts() -> dict[Path, str]:
    return {}


@dataclass(frozen=True)
class Fence:
    """ One fenced code block.

    ``body_lines`` is the text inside the fence, without the backtick
    lines. ``body_line`` is the 1-based Markdown line of
    ``body_lines[0]`` when the body is not empty. ``open_line`` is the
    opening backtick line. ``attrs`` holds ``key=value`` words from
    the info string, such as ``file``.
    """

    path: Path
    info: str
    language: str
    attrs: Mapping[str, str]
    body_lines: tuple[str, ...]
    open_line: int
    body_line: int


@dataclass(frozen=True)
class Link:
    """ One Markdown link. ``target`` is the href as written. """

    path: Path
    line: int
    target: str
    text: str


@dataclass(frozen=True)
class Heading:
    """ One ATX heading. ``slug`` comes from the shared slug function. """

    path: Path
    line: int
    level: int
    slug: str


@dataclass(frozen=True)
class Document:
    """ One parsed Markdown file. Paths are relative to the book root. """

    path: Path
    fences: tuple[Fence, ...]
    headings: tuple[Heading, ...]
    links: tuple[Link, ...]


@dataclass(frozen=True)
class Diagnostic:
    """ A tangle error, link warning, or lint finding.

    ``line`` is a 1-based line in ``path``. ``severity`` is ``error``
    or ``warning``. ``code`` is a short stable identifier.
    """

    path: Path
    line: int
    severity: Severity
    code: str
    message: str


class UnsafeOutputPath(Exception):
    """ An output path is empty, absolute, or leaves the target.

    ``raw`` is the path that was refused, also included in the message.
    """

    raw: str

    def __init__(self, raw: str) -> None:
        self.raw = raw
        super().__init__(f"output path escapes the target: {raw!r}")


@dataclass(frozen=True)
class OutputPath:
    """ A target-relative path that passed ``vet_output_path``. """

    path: Path


@dataclass(frozen=True)
class RejectedPath:
    """ A path ``vet_output_path`` refused.

    ``escapes`` is true for absolute paths, backslashes, and ``..``
    that survives normalization. It is false for an empty path, a
    NUL, or a path that normalizes to ``.``.
    """

    raw: str
    escapes: bool


def vet_output_path(raw: str) -> OutputPath | RejectedPath:
    """ Classify ``raw`` as a safe relative path or a rejection.

    ``a/../b`` is safe and becomes ``b``. This is the containment rule
    for fences, ``OutputFile``, mounts, and the writer. It does not
    resolve symlinks.
    """
    if _malformed_text(raw):
        return RejectedPath(raw, escapes=False)
    if "\\" in raw or raw.startswith("/") or _leaves_root(raw):
        return RejectedPath(raw, escapes=True)
    normalized = posixpath.normpath(raw)
    if normalized == ".":
        return RejectedPath(raw, escapes=False)
    return OutputPath(Path(normalized))


# Not valid in a Windows file name, so a book using them would not
# tangle on every platform. Control characters (including NUL) too.
_PORTABILITY_FORBIDDEN = frozenset('<>:"|?*')


def _malformed_text(raw: str) -> bool:
    return raw == "" or any(
        char in _PORTABILITY_FORBIDDEN or ord(char) < 32 for char in raw
    )


def _leaves_root(raw: str) -> bool:
    normalized = posixpath.normpath(raw)
    return normalized == ".." or normalized.startswith("../")


@dataclass(frozen=True)
class OutputFile:
    """ The bytes of one relative output path.

    Construction rejects a path that fails ``vet_output_path`` and
    stores the normalized form.
    """

    path: Path
    data: bytes

    def __post_init__(self) -> None:
        verdict = vet_output_path(self.path.as_posix())
        if isinstance(verdict, RejectedPath):
            raise UnsafeOutputPath(self.path.as_posix())
        object.__setattr__(self, "path", verdict.path)


@dataclass(frozen=True)
class FileSet:
    """ Relative output paths and the bytes to write for them.

    This is pure data. Writing it to disk is the writer's job.
    """

    files: tuple[OutputFile, ...] = ()

    def data_for(self, path: Path) -> bytes | None:
        """ Return the bytes for ``path``, or None when it is absent. """
        for item in self.files:
            if item.path == path:
                return item.data
        return None


@dataclass(frozen=True)
class Book:
    """ Every document under a source root, in tangle order.

    ``diagnostics`` holds problems found while reading the documents,
    such as a fence that never closes. Later layers add their own.
    ``texts`` is the Markdown each document was parsed from, including
    unsaved buffer text that is not on disk.
    """

    root: Path
    documents: tuple[Document, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
    texts: Mapping[Path, str] = field(default_factory=_empty_texts)
