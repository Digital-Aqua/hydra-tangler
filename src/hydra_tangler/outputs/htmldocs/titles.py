""" Choose the navigation title of a document.

The title is the plain text of the first ATX heading. When the
document has no heading, the filename stem is used. This does not
assign heading ids.
"""

from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.token import Token


def document_title(text: str, source: Path) -> str:
    """ Return the title to show for ``source``. """
    tokens = MarkdownIt("commonmark", {"html": False}).parse(text)
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        title = _plain_text(tokens, index)
        if title:
            return title
    return source.stem


def _plain_text(tokens: list[Token], index: int) -> str:
    nxt = index + 1
    if nxt >= len(tokens) or tokens[nxt].type != "inline":
        return ""
    parts: list[str] = []
    for child in tokens[nxt].children or []:
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
    return "".join(parts).strip()
