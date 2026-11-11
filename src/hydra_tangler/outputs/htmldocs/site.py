""" Assemble a book into the HTML docs FileSet.

The site index is the root document ``index.md`` when that file
exists. Otherwise ``index.html`` is a generated table of contents in
document order, and every Markdown file still has its own page.
This module does not write the output directory, does not check
links, and builds no source map: a page is not a line-for-line
translation of its Markdown.
"""

from importlib.resources import files
from pathlib import Path

from hydra_tangler.model import Book, Document, FileSet, OutputFile
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.outputs.htmldocs.context import DocPage, NavNode, Neighbour
from hydra_tangler.outputs.htmldocs.highlight import pygments_stylesheet
from hydra_tangler.outputs.htmldocs.listing import file_groups
from hydra_tangler.outputs.htmldocs.navigation import navigation_nodes
from hydra_tangler.outputs.htmldocs.render import render_article
from hydra_tangler.outputs.htmldocs.shell import document_shell, plain_shell
from hydra_tangler.outputs.htmldocs.templates_env import render_template
from hydra_tangler.outputs.htmldocs.titles import document_title
from hydra_tangler.outputs.htmldocs.urls import (
    FILES_PAGE,
    HOME_PAGE,
    PYGMENTS_CSS,
    SITE_CSS,
    html_path,
    relative_url,
)
from hydra_tangler.sourcemap import SourceMap

_ROOT_INDEX = "index.md"


def render_book(book: Book) -> Rendered:
    """ Return the static site for ``book``. """
    texts = _read(book)
    pages = _doc_pages(book, texts)
    nodes = navigation_nodes(pages)
    output = _documents(book, texts, pages, nodes)
    if _root_index(pages) is None:
        output.append(_contents(pages, nodes))
    output.append(_files_page(book, nodes))
    output.extend(_assets())
    return Rendered(FileSet(tuple(output)), SourceMap())


def _read(book: Book) -> dict[Path, str]:
    return {
        document.path: _text(book, document.path)
        for document in book.documents
    }


def _text(book: Book, relative: Path) -> str:
    """ The text the book was parsed from, otherwise the file on disk. """
    if relative in book.texts:
        return book.texts[relative]
    path = book.root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _doc_pages(book: Book, texts: dict[Path, str]) -> tuple[DocPage, ...]:
    return tuple(
        DocPage(
            document.path,
            html_path(document.path),
            document_title(texts[document.path], document.path),
        )
        for document in book.documents
    )


def _root_index(pages: tuple[DocPage, ...]) -> DocPage | None:
    for page in pages:
        if page.source.as_posix() == _ROOT_INDEX:
            return page
    return None


def _documents(
    book: Book,
    texts: dict[Path, str],
    pages: tuple[DocPage, ...],
    nodes: tuple[NavNode, ...],
) -> list[OutputFile]:
    return [
        _document(texts[document.path], document, page, pages, nodes)
        for document, page in zip(book.documents, pages, strict=True)
    ]


def _document(
    text: str,
    document: Document,
    page: DocPage,
    pages: tuple[DocPage, ...],
    nodes: tuple[NavNode, ...],
) -> OutputFile:
    parts = render_article(text, document, page.output)
    shell = document_shell(page, pages, nodes)
    html = render_template("page.html.j2", shell=shell, parts=parts)
    return OutputFile(page.output, html.encode("utf-8"))


def _contents(
    pages: tuple[DocPage, ...],
    nodes: tuple[NavNode, ...],
) -> OutputFile:
    entries = tuple(_entry(page) for page in pages)
    html = render_template(
        "index.html.j2",
        shell=plain_shell("Contents", HOME_PAGE, nodes),
        entries=entries,
    )
    return OutputFile(HOME_PAGE, html.encode("utf-8"))


def _entry(page: DocPage) -> Neighbour:
    return Neighbour(page.title, relative_url(HOME_PAGE, page.output))


def _files_page(book: Book, nodes: tuple[NavNode, ...]) -> OutputFile:
    html = render_template(
        "files.html.j2",
        shell=plain_shell("Files", FILES_PAGE, nodes),
        groups=file_groups(book, FILES_PAGE),
    )
    return OutputFile(FILES_PAGE, html.encode("utf-8"))


def _assets() -> tuple[OutputFile, ...]:
    css = files("hydra_tangler.outputs.htmldocs").joinpath("static/site.css")
    site = css.read_text(encoding="utf-8").encode("utf-8")
    pygments = pygments_stylesheet().encode("utf-8")
    return (
        OutputFile(SITE_CSS, site),
        OutputFile(PYGMENTS_CSS, pygments),
    )
