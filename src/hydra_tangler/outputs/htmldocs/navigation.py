""" Build the left-hand navigation tree.

Directories and documents are ordered alphabetically by path segment.
A document's label is its title. This module does not render HTML.
Relative hrefs are filled in for one page at a time.
"""

from collections.abc import Sequence
from pathlib import Path

from hydra_tangler.outputs.htmldocs.context import DocPage, NavItem, NavNode
from hydra_tangler.outputs.htmldocs.urls import relative_url


def navigation_nodes(pages: Sequence[DocPage]) -> tuple[NavNode, ...]:
    """ Return the site tree for ``pages`` in one directory level. """
    return _level(pages, depth=0)


def navigation_for(
    nodes: Sequence[NavNode],
    page: Path,
) -> tuple[NavItem, ...]:
    """ Return ``nodes`` with hrefs relative to ``page``. """
    return tuple(_item(node, page) for node in nodes)


def _level(pages: Sequence[DocPage], depth: int) -> tuple[NavNode, ...]:
    folders: dict[str, list[DocPage]] = {}
    files: list[NavNode] = []
    for page in pages:
        parts = page.source.parts
        if len(parts) == depth + 1:
            files.append(_file_node(page))
            continue
        folders.setdefault(parts[depth], []).append(page)
    folders_nodes = [
        _folder_node(name, grouped, depth) for name, grouped in folders.items()
    ]
    ordered = sorted([*files, *folders_nodes], key=lambda node: node.order_name)
    return tuple(ordered)


def _folder_node(
    name: str,
    pages: Sequence[DocPage],
    depth: int,
) -> NavNode:
    return NavNode(name, name, None, _level(pages, depth + 1))


def _file_node(page: DocPage) -> NavNode:
    return NavNode(page.title, page.source.name, page.output, ())


def _item(node: NavNode, page: Path) -> NavItem:
    href = None
    current = False
    if node.target is not None:
        href = relative_url(page, node.target)
        current = node.target == page
    children = tuple(_item(child, page) for child in node.children)
    return NavItem(node.title, href, current, children)
