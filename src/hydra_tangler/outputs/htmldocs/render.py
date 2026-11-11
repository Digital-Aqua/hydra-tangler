""" Render one Markdown document to article parts.

Heading ids and link rewriting happen here.
Fenced code is a separate part so the page template can draw it with
the code-block macro, copying the fence's marker onto that element.
This module does not build navigation, the source map, or the site.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
from markdown_it.token import Token
from markdown_it.utils import EnvType, OptionsDict
from markupsafe import Markup

from hydra_tangler.model import Document, Fence
from hydra_tangler.outputs.htmldocs.headings import assign_heading_ids
from hydra_tangler.outputs.htmldocs.highlight import highlighted_html
from hydra_tangler.outputs.htmldocs.links import apply_link


class FenceMismatch(Exception):
    """ The renderer saw a different fence count than the parser. """


@dataclass(frozen=True)
class ArticlePart:
    """ One slice of an article: prose HTML or a highlighted fence. """

    kind: Literal["prose", "code"]
    html: Markup
    anchor: str | None = None
    output_path: str | None = None
    language: str = ""


class DocsRenderer(RendererHTML):
    """ CommonMark HTML with links rewritten for the static site. """

    source: Path
    page: Path

    def __init__(self, parser: MarkdownIt | None = None) -> None:
        self.source = Path()
        self.page = Path()
        super().__init__(parser)

    def link_open(
        self,
        tokens: Sequence[Token],
        idx: int,
        options: OptionsDict,
        env: EnvType,
    ) -> str:
        """ Rewrite the href, then render the opening tag. """
        apply_link(tokens[idx], self.source, self.page)
        return self.renderToken(tokens, idx, options, env)


def render_article(
    text: str,
    document: Document,
    page: Path,
) -> tuple[ArticlePart, ...]:
    """ Return prose and code parts for ``document``. """
    parser = _parser()
    tokens = parser.parse(text)
    assign_heading_ids(tokens, document.headings, document.path)
    fences = _fence_map(tokens, document.fences, document.path)
    return _parts(parser, tokens, fences, document.path, page)


def fence_anchor(source: Path, open_line: int) -> str:
    """ Return the element id for a fence that writes an output file. """
    flat = source.as_posix().replace("/", "-").replace(".", "-")
    return f"fence-{flat}-line-{open_line}"


def _parser() -> MarkdownIt:
    parser = MarkdownIt(
        "commonmark",
        {"html": False},
        renderer_cls=DocsRenderer,
    )
    return parser.enable("table")


def _parts(
    parser: MarkdownIt,
    tokens: Sequence[Token],
    fences: dict[int, Fence],
    source: Path,
    page: Path,
) -> tuple[ArticlePart, ...]:
    buffer: list[Token] = []
    parts: list[ArticlePart] = []
    for token in tokens:
        if token.type != "fence":
            buffer.append(token)
            continue
        _flush(parts, parser, buffer, source, page)
        buffer = []
        parts.append(_code_part(token, fences.get(id(token))))
    _flush(parts, parser, buffer, source, page)
    return tuple(parts)


def _flush(
    parts: list[ArticlePart],
    parser: MarkdownIt,
    tokens: list[Token],
    source: Path,
    page: Path,
) -> None:
    if not tokens:
        return
    renderer = parser.renderer
    if not isinstance(renderer, DocsRenderer):
        raise FenceMismatch(
            f"{source.as_posix()}: docs renderer is not installed"
        )
    renderer.source = source
    renderer.page = page
    html = renderer.render(tokens, parser.options, {})
    parts.append(ArticlePart("prose", Markup(html)))


def _code_part(token: Token, fence: Fence | None) -> ArticlePart:
    language = fence.language if fence is not None else ""
    anchor, output_path = _fence_label(fence)
    code = Markup(highlighted_html(token.content, language))
    return ArticlePart(
        "code",
        code,
        anchor,
        output_path,
        language,
    )


def _fence_map(
    tokens: Sequence[Token],
    fences: Sequence[Fence],
    document: Path,
) -> dict[int, Fence]:
    found = [token for token in tokens if token.type == "fence"]
    if len(found) != len(fences):
        place = document.as_posix()
        raise FenceMismatch(
            f"{place}: expected {len(fences)} fences, found {len(found)}"
        )
    paired = zip(found, fences, strict=True)
    return {id(token): fence for token, fence in paired}


def _fence_label(fence: Fence | None) -> tuple[str | None, str | None]:
    if fence is None:
        return None, None
    output_path = fence.attrs.get("file", "")
    if output_path == "":
        return None, None
    return fence_anchor(fence.path, fence.open_line), output_path
