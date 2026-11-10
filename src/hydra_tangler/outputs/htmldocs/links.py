""" Rewrite links while a Markdown document is rendered.

Links to other ``.md`` files become links to the generated HTML
pages, including any fragment. Other relative links are left as
written. External links are flagged so the renderer can add
``rel="noopener"``. This module does not report dead links.
"""

import posixpath
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import SplitResult, urlsplit

from markdown_it.token import Token

from hydra_tangler.outputs.htmldocs.urls import html_path, relative_url


@dataclass(frozen=True)
class RewrittenHref:
    """ An href after static-site rewriting. """

    href: str
    external: bool


def apply_link(token: Token, source: Path, page: Path) -> None:
    """ Rewrite one link token in place. """
    href = token.attrGet("href")
    if not isinstance(href, str):
        return
    rewritten = rewrite_href(href, source, page)
    token.attrSet("href", rewritten.href)
    if rewritten.external:
        _set_noopener(token)


def rewrite_href(href: str, source: Path, page: Path) -> RewrittenHref:
    """ Return the href a static page should use. """
    if href.startswith("#") or href == "":
        return RewrittenHref(href, False)
    pieces = urlsplit(href)
    if _is_external(pieces) or pieces.path.startswith("/"):
        return RewrittenHref(href, _is_external(pieces))
    if not pieces.path.endswith(".md"):
        return RewrittenHref(href, False)
    target = _html_target(source, pieces.path)
    relative = relative_url(page, target)
    href = _attach(relative, pieces.query, pieces.fragment)
    return RewrittenHref(href, False)


def _is_external(pieces: SplitResult) -> bool:
    return bool(pieces.scheme or pieces.netloc)


def _html_target(source: Path, markdown_path: str) -> Path:
    joined = (source.parent / markdown_path).as_posix()
    return html_path(Path(posixpath.normpath(joined)))


def _attach(path: str, query: str, fragment: str) -> str:
    if query:
        path = f"{path}?{query}"
    if fragment:
        path = f"{path}#{fragment}"
    return path


def _set_noopener(token: Token) -> None:
    current = token.attrGet("rel")
    if current is None:
        token.attrSet("rel", "noopener")
        return
    words = str(current).split()
    if "noopener" in words:
        return
    token.attrSet("rel", f"{current} noopener")
