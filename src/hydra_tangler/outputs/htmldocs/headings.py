""" Put the shared heading slugs onto rendered headings.

Ids are computed with ``unique_slug`` from the same inline text the
parser stores, in document order. A mismatch with ``Document.headings``
is an error. This module does not render the heading body.
"""

from collections.abc import Sequence
from pathlib import Path

from markdown_it.token import Token

from hydra_tangler.model import Heading
from hydra_tangler.slug import unique_slug


class HeadingSlugMismatch(Exception):
    """ Rendered heading slugs would disagree with the document. """


def assign_heading_ids(
    tokens: Sequence[Token],
    headings: Sequence[Heading],
    document: Path,
) -> None:
    """ Set ``id`` on each top-level heading opening token. """
    seen: dict[str, int] = {}
    index = 0
    for position, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        slug = unique_slug(_inline_content(tokens, position), seen)
        _check(document, slug, headings, index)
        token.attrSet("id", slug)
        index += 1
    if index != len(headings):
        raise HeadingSlugMismatch(_count(document, len(headings), index))


def _check(
    document: Path,
    slug: str,
    headings: Sequence[Heading],
    index: int,
) -> None:
    if index >= len(headings):
        raise HeadingSlugMismatch(_count(document, len(headings), index + 1))
    if headings[index].slug == slug:
        return
    expected = headings[index].slug
    place = document.as_posix()
    raise HeadingSlugMismatch(
        f"{place}: expected heading slug {expected!r}, found {slug!r}"
    )


def _count(document: Path, expected: int, actual: int) -> str:
    return (
        f"{document.as_posix()}: expected {expected} headings, found {actual}"
    )


def _inline_content(tokens: Sequence[Token], index: int) -> str:
    nxt = index + 1
    if nxt >= len(tokens):
        return ""
    if tokens[nxt].type != "inline":
        return ""
    return tokens[nxt].content
