""" Warn about relative links that miss their target.

A link with a scheme, a ``mailto:`` link, a protocol-relative URL,
or a site-absolute path is left alone. Anchors are compared with
``Heading.slug`` already stored on each document. This module does
not invent a second slug and does not look at the network.
"""

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from hydra_tangler.model import Book, Diagnostic, Document, Link

_KIND = Literal["external", "same", "file"]


@dataclass(frozen=True)
class _Target:
    """ A link after scheme and fragment splitting. """

    kind: _KIND
    path: Path | None = None
    anchor: str | None = None


def find_dead_links(book: Book) -> tuple[Diagnostic, ...]:
    """ Return warning diagnostics for broken relative links. """
    documents = {item.path: item for item in book.documents}
    found: list[Diagnostic] = []
    for document in book.documents:
        for link in document.links:
            found.extend(_check(book, documents, document, link))
    return tuple(found)


def _check(
    book: Book,
    documents: dict[Path, Document],
    document: Document,
    link: Link,
) -> tuple[Diagnostic, ...]:
    target = _classify(document.path, link.target)
    if target.kind == "external":
        return ()
    if target.kind == "same":
        return _anchor(document, link, target.anchor)
    return _file_link(book, documents, link, target)


def _file_link(
    book: Book,
    documents: dict[Path, Document],
    link: Link,
    target: _Target,
) -> tuple[Diagnostic, ...]:
    path = target.path
    if path is None or not _exists(book, documents, path):
        return (
            _warning(
                link,
                "dead-link",
                f"link target does not exist: {link.target}",
            ),
        )
    linked = documents.get(path)
    if linked is None:
        return ()
    return _anchor(linked, link, target.anchor)


def _anchor(
    linked: Document,
    link: Link,
    anchor: str | None,
) -> tuple[Diagnostic, ...]:
    if anchor is None:
        return ()
    for heading in linked.headings:
        if heading.slug == anchor:
            return ()
    return (_warning(link, "dead-anchor", f"heading not found: #{anchor}"),)


def _exists(
    book: Book,
    documents: dict[Path, Document],
    relative: Path,
) -> bool:
    if relative in documents:
        return True
    return (book.root / relative).is_file()


def _warning(link: Link, code: str, message: str) -> Diagnostic:
    return Diagnostic(link.path, link.line, "warning", code, message)


def _classify(document: Path, raw: str) -> _Target:
    if _is_external(raw):
        return _Target("external")
    parts = urlsplit(raw)
    anchor = parts.fragment or None
    if not parts.path:
        return _Target("same", anchor=anchor)
    relative = _resolve(document, parts.path)
    if relative is None:
        return _Target("file", path=None, anchor=anchor)
    return _Target("file", path=relative, anchor=anchor)


def _is_external(raw: str) -> bool:
    if raw.startswith("//") or raw.startswith("/"):
        return True
    parts = urlsplit(raw)
    return bool(parts.scheme)


def _resolve(document: Path, href_path: str) -> Path | None:
    joined = posixpath.normpath(
        (document.parent / href_path).as_posix()
    )
    if joined == ".." or joined.startswith("../"):
        return None
    return Path(joined)
