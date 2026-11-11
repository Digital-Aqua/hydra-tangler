""" Parse one Markdown string into a Document.

Uses markdown-it-py's CommonMark tokens, so a longer backtick run
encloses a shorter one. Line numbers come from ``token.map`` and are
1-based. This module does not read or write files.
"""

import re
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from markdown_it import MarkdownIt
from markdown_it.token import Token

from hydra_tangler.model import (
    Diagnostic,
    Document,
    Fence,
    Heading,
    Link,
)
from hydra_tangler.slug import unique_slug

_CLOSING_FENCE = re.compile(r" {0,3}(`{3,})\s*$")


@dataclass(frozen=True)
class Parsed:
    """ A document and the problems found while reading it. """

    document: Document
    diagnostics: tuple[Diagnostic, ...]


def parse_document(text: str, path: Path) -> Parsed:
    """ Return the fences, headings, and links in ``text``. """
    tokens = MarkdownIt("commonmark").parse(text)
    fences, diagnostics = _fences(tokens, text, path)
    document = Document(
        path,
        fences,
        _headings(tokens, path),
        _links(tokens, path),
    )
    return Parsed(document, diagnostics)


def _fences(
    tokens: list[Token],
    text: str,
    path: Path,
) -> tuple[tuple[Fence, ...], tuple[Diagnostic, ...]]:
    found: list[Fence] = []
    problems: list[Diagnostic] = []
    for token in tokens:
        if token.type != "fence":
            continue
        problem = _unclosed(token, text, path)
        if problem is not None:
            problems.append(problem)
        info = _read_info(token.info)
        if info.error is not None:
            problems.append(_bad_attrs(path, token, info.error))
            continue
        found.append(_fence(token, path, info))
    return tuple(found), tuple(problems)


@dataclass(frozen=True)
class _Info:
    """ The language tag and attributes of one info string. """

    language: str
    attrs: Mapping[str, str]
    error: str | None = None


def _fence(token: Token, path: Path, info: _Info) -> Fence:
    open_line = _line(token)
    body = tuple(token.content.splitlines())
    return Fence(
        path,
        token.info,
        info.language,
        info.attrs,
        body,
        open_line,
        open_line + 1,
    )


def _read_info(info: str) -> _Info:
    try:
        parts = shlex.split(info)
    except ValueError as err:
        return _Info("", MappingProxyType({}), str(err))
    language = ""
    pairs: dict[str, str] = {}
    for index, part in enumerate(parts):
        if "=" in part:
            key, _, value = part.partition("=")
            pairs[key] = value
            continue
        if index == 0:
            language = part
    return _Info(language, MappingProxyType(pairs))


def _bad_attrs(path: Path, token: Token, detail: str) -> Diagnostic:
    return Diagnostic(
        path,
        _line(token),
        "warning",
        "bad-fence-attrs",
        f"bad fence attributes: {detail}",
    )


def _unclosed(token: Token, text: str, path: Path) -> Diagnostic | None:
    if _fence_is_closed(token, text):
        return None
    return Diagnostic(
        path,
        _line(token),
        "error",
        "unclosed-fence",
        "fence is never closed",
    )


def _fence_is_closed(token: Token, text: str) -> bool:
    if token.map is None:
        return False
    lines = text.splitlines()
    end = token.map[1]
    if end < 1 or end > len(lines):
        return False
    return _is_closing_line(lines[end - 1], len(token.markup))


def _is_closing_line(line: str, opener_length: int) -> bool:
    match = _CLOSING_FENCE.match(line)
    if match is None:
        return False
    return len(match.group(1)) >= opener_length


def _headings(tokens: list[Token], path: Path) -> tuple[Heading, ...]:
    seen: dict[str, int] = {}
    found: list[Heading] = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open":
            continue
        title = _heading_text(tokens, index)
        found.append(
            Heading(
                path,
                _line(token),
                _level(token),
                unique_slug(title, seen),
            )
        )
    return tuple(found)


def _heading_text(tokens: list[Token], index: int) -> str:
    nxt = index + 1
    if nxt >= len(tokens):
        return ""
    if tokens[nxt].type != "inline":
        return ""
    return tokens[nxt].content


def _level(token: Token) -> int:
    if len(token.tag) == 2 and token.tag[1].isdigit():
        return int(token.tag[1])
    return 1


def _links(tokens: list[Token], path: Path) -> tuple[Link, ...]:
    found: list[Link] = []
    for token in tokens:
        if token.type != "inline" or not token.children:
            continue
        found.extend(_inline_links(token, path))
    return tuple(found)


def _inline_links(token: Token, path: Path) -> tuple[Link, ...]:
    children = token.children or []
    line = _line(token)
    found: list[Link] = []
    index = 0
    while index < len(children):
        child = children[index]
        if child.type != "link_open":
            index += 1
            continue
        text, index = _link_text(children, index + 1)
        found.append(Link(path, line, _href(child), text))
    return tuple(found)


def _link_text(children: list[Token], start: int) -> tuple[str, int]:
    parts: list[str] = []
    index = start
    while index < len(children):
        child = children[index]
        if child.type == "link_close":
            return "".join(parts), index + 1
        if child.type in ("text", "code_inline"):
            parts.append(child.content)
        index += 1
    return "".join(parts), index


def _href(token: Token) -> str:
    return str(token.attrs.get("href", ""))


def _line(token: Token) -> int:
    if token.map is None:
        return 1
    return token.map[0] + 1
