""" Site paths and relative links between pages.

A Markdown path ``foo/bar.md`` becomes ``foo/bar.html``. This module
does not rewrite hrefs inside a document and does not render HTML.
"""

import posixpath
from pathlib import Path

HOME_PAGE = Path("index.html")
FILES_PAGE = Path("files.html")
SITE_CSS = Path("_assets/site.css")
PYGMENTS_CSS = Path("_assets/pygments.css")


def html_path(source: Path) -> Path:
    """ Return the page path for one Markdown document. """
    return source.with_suffix(".html")


def relative_url(origin: Path, target: Path) -> str:
    """ Return the href from the page ``origin`` to ``target``.

    Both arguments are site-relative paths with forward slashes.
    """
    start = origin.parent.as_posix() or "."
    return posixpath.relpath(target.as_posix(), start)


def anchored(origin: Path, target: Path, anchor: str) -> str:
    """ Return a relative href that includes a fragment. """
    return f"{relative_url(origin, target)}#{anchor}"
