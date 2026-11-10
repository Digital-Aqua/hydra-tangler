""" Template values for the HTML docs site.

Frozen data only. Building these values, rendering Markdown, and
writing files happen in the neighbouring modules.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocPage:
    """ One Markdown document and the page path it renders to. """

    source: Path
    output: Path
    title: str


@dataclass(frozen=True)
class Neighbour:
    """ A link to another page in this site. """

    title: str
    href: str


@dataclass(frozen=True)
class FilesLink:
    """ The tangled-files page, as seen from the current page. """

    href: str
    current: bool


@dataclass(frozen=True)
class NavItem:
    """ One row of the navigation tree, already relative. """

    title: str
    href: str | None
    current: bool
    children: tuple[NavItem, ...]


@dataclass(frozen=True)
class Shell:
    """ The layout shared by every page. """

    title: str
    home_href: str
    on_home: bool
    navigation: tuple[NavItem, ...]
    previous: Neighbour | None
    next_page: Neighbour | None
    files_link: FilesLink
    site_css: str
    pygments_css: str


@dataclass(frozen=True)
class FileGroup:
    """ One tangled output path and the fences that contribute to it. """

    path: str
    sources: tuple[Neighbour, ...]


@dataclass(frozen=True)
class NavNode:
    """ A directory or document before links are made relative.

    ``order_name`` is the filename or directory name used for sorting.
    Templates never see this type.
    """

    title: str
    order_name: str
    target: Path | None
    children: tuple[NavNode, ...]
