""" Plain data shared by every layer.

These types carry parsed documents, diagnostics, and the bytes an
output wants written. They do not read files, write files, or decide
what a fence means.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

Severity = Literal["error", "warning"]


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


@dataclass(frozen=True)
class OutputFile:
    """ The bytes of one relative output path. """

    path: Path
    data: bytes


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
    """

    root: Path
    documents: tuple[Document, ...]
    diagnostics: tuple[Diagnostic, ...] = ()
