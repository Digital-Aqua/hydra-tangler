""" Fill the shared page shell for one output path.

Navigation hrefs, the home link, and the files link are relative to
the page being rendered. Previous and next follow document order and
are omitted for the generated contents page and the files page.
"""

from collections.abc import Sequence
from pathlib import Path

from hydra_tangler.outputs.htmldocs.context import (
    DocPage,
    FilesLink,
    NavNode,
    Neighbour,
    Shell,
)
from hydra_tangler.outputs.htmldocs.navigation import navigation_for
from hydra_tangler.outputs.htmldocs.urls import (
    FILES_PAGE,
    HOME_PAGE,
    PYGMENTS_CSS,
    SITE_CSS,
    relative_url,
)


def document_shell(
    page: DocPage,
    pages: Sequence[DocPage],
    nodes: Sequence[NavNode],
) -> Shell:
    """ Return the shell for a document page, with its neighbours. """
    return _shell(
        page.title,
        page.output,
        nodes,
        *_neighbours(page, pages),
    )


def plain_shell(
    title: str,
    page: Path,
    nodes: Sequence[NavNode],
) -> Shell:
    """ Return a shell with no previous or next link. """
    return _shell(title, page, nodes, None, None)


def _shell(
    title: str,
    page: Path,
    nodes: Sequence[NavNode],
    previous: Neighbour | None,
    following: Neighbour | None,
) -> Shell:
    return Shell(
        title,
        relative_url(page, HOME_PAGE),
        page == HOME_PAGE,
        navigation_for(nodes, page),
        previous,
        following,
        FilesLink(relative_url(page, FILES_PAGE), page == FILES_PAGE),
        relative_url(page, SITE_CSS),
        relative_url(page, PYGMENTS_CSS),
    )


def _neighbours(
    page: DocPage,
    pages: Sequence[DocPage],
) -> tuple[Neighbour | None, Neighbour | None]:
    index = _index_of(page, pages)
    previous = _at(pages, index - 1, page.output) if index > 0 else None
    following = None
    if index + 1 < len(pages):
        following = _at(pages, index + 1, page.output)
    return previous, following


def _at(pages: Sequence[DocPage], index: int, origin: Path) -> Neighbour:
    page = pages[index]
    return Neighbour(page.title, relative_url(origin, page.output))


def _index_of(page: DocPage, pages: Sequence[DocPage]) -> int:
    for index, item in enumerate(pages):
        if item.source == page.source:
            return index
    return 0
