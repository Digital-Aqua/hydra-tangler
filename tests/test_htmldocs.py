""" HTML docs: pages, heading ids, links, navigation, and files. """

import re
from pathlib import Path

from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.model import Book
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.outputs.htmldocs import output
from hydra_tangler.outputs.htmldocs.context import DocPage
from hydra_tangler.outputs.htmldocs.links import rewrite_href
from hydra_tangler.outputs.htmldocs.navigation import navigation_nodes
from hydra_tangler.outputs.htmldocs.urls import html_path, relative_url
from hydra_tangler.parse import parse_document

_HEADING_ID = re.compile(r"<h([1-6]) id=\"([^\"]*)\"")


def test_heading_ids_match_document_slugs(tmp_path: Path) -> None:
    text = (
        "# What's up?\n\n"
        "## What's up?\n\n"
        "# Hello, world!\n\n"
        "## Hello, world!\n"
    )
    write_chapter(tmp_path, "notes/second.md", text)
    rendered = output.render(load_book(tmp_path))
    page = _text(rendered, "notes/second.html")
    parsed = parse_document(text, Path("notes/second.md"))
    slugs = [item.slug for item in parsed.document.headings]
    assert _heading_ids(page) == slugs


def test_link_rewriting_keeps_anchors_and_external_rel() -> None:
    page = html_path(Path("notes/second.md"))
    source = Path("notes/second.md")
    rewritten = rewrite_href("../alpha/intro.md#intro", source, page)
    assert rewritten.href == "../alpha/intro.html#intro"
    assert rewritten.external is False
    picture = rewrite_href("picture.png", source, page)
    assert picture.href == "picture.png"
    assert picture.external is False
    web = rewrite_href("https://example.com/docs", source, page)
    assert web.href == "https://example.com/docs"
    assert web.external is True
    missing = rewrite_href("missing.md", source, page)
    assert missing.href == "missing.html"


def test_relative_url_between_pages() -> None:
    origin = Path("notes/second.html")
    target = Path("alpha/intro.html")
    assert relative_url(origin, target) == "../alpha/intro.html"
    assert relative_url(Path("index.html"), Path("_assets/site.css")) == (
        "_assets/site.css"
    )


def test_site_pages(snapshot: object, tmp_path: Path) -> None:
    book = _fixture(tmp_path)
    rendered = output.render(book)
    pages = {
        item.path.as_posix(): item.data.decode("utf-8")
        for item in rendered.files.files
        if item.path.suffix == ".html"
    }
    assert pages == snapshot
    intro = pages["alpha/intro.html"]
    second = pages["notes/second.html"]
    third = pages["notes/third.html"]
    files = pages["files.html"]
    assert 'class="previous"' not in intro
    assert 'href="../notes/second.html"' in intro
    assert 'href="../alpha/intro.html"' in second
    assert 'href="third.html"' in second
    assert 'href="second.html"' in third
    assert 'class="next"' not in third
    assert 'rel="noopener"' in second
    assert 'href="picture.png"' in second
    assert 'href="missing.html"' in second
    assert 'href="../alpha/intro.html#intro"' in second
    assert "<table>" in intro
    assert 'id="fence-alpha-intro-md-line-' in intro
    assert "src/app.py" in intro
    assert "src/raw.txt" in files
    assert "src/app.py" in files
    assert files.index("src/app.py") < files.index("src/raw.txt")
    assert files.count("alpha/intro.html#fence-") == 3
    assert "print(&quot;loose&quot;)" not in intro
    assert "<span" in intro
    contents = pages["index.html"]
    assert ">Intro<" in contents
    assert ">What&#39;s up?<" in contents
    assert ">Third<" in contents


def test_root_index_md_is_the_home_page(tmp_path: Path) -> None:
    write_chapter(tmp_path, "index.md", "# Welcome\n")
    write_chapter(tmp_path, "alpha/intro.md", "# Intro\n")
    rendered = output.render(load_book(tmp_path))
    home = _text(rendered, "index.html")
    assert 'id="welcome"' in home
    assert "<h1>Contents</h1>" not in home


def test_navigation_is_alphabetical(tmp_path: Path) -> None:
    book = _fixture(tmp_path)
    rendered = output.render(book)
    pages = _doc_pages(book)
    nodes = navigation_nodes(pages)
    assert [node.order_name for node in nodes] == ["alpha", "notes"]
    assert [node.title for node in nodes[0].children] == ["Intro"]
    notes = [node.title for node in nodes[1].children]
    assert notes == ["What's up?", "Third"]
    intro = _text(rendered, "alpha/intro.html")
    alpha = intro.split('class="folder"', 1)[1]
    assert alpha.index("Intro") < alpha.index("What&#39;s up?")
    assert 'aria-current="page"' in intro


def _fixture(root: Path) -> Book:
    write_chapter(
        root,
        "alpha/intro.md",
        "\n".join(
            (
                "# Intro",
                "",
                "A table.",
                "",
                "| Col | Val |",
                "| --- | --- |",
                "| a | b |",
                "",
                fence("python file=src/app.py", 'print("hi")'),
                fence("python file=src/app.py", 'print("again")'),
                fence("notalang file=src/raw.txt", "@@@"),
                fence("python", 'print("loose")'),
            )
        ),
    )
    write_chapter(
        root,
        "notes/second.md",
        "\n".join(
            (
                "# What's up?",
                "",
                "## What's up?",
                "",
                "A [picture](picture.png), a [missing](missing.md),",
                "and a [web](https://example.com/docs).",
                "",
                "Back to [intro](../alpha/intro.md#intro).",
                "",
            )
        ),
    )
    write_chapter(root, "notes/third.md", "# Third\n\nLast page.\n")
    return load_book(root)


def _doc_pages(book: Book) -> tuple[DocPage, ...]:
    from hydra_tangler.outputs.htmldocs.titles import document_title

    pages: list[DocPage] = []
    for document in book.documents:
        text = (book.root / document.path).read_text(encoding="utf-8")
        pages.append(
            DocPage(
                document.path,
                html_path(document.path),
                document_title(text, document.path),
            )
        )
    return tuple(pages)


def _text(rendered: Rendered, relative: str) -> str:
    data = rendered.files.data_for(Path(relative))
    assert data is not None
    return data.decode("utf-8")


def _heading_ids(html: str) -> list[str]:
    return [match.group(2) for match in _HEADING_ID.finditer(html)]
