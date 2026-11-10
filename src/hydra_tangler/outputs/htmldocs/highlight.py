""" Highlight fenced code with Pygments at build time.

Unknown language names fall back to plain text. This module does not
emit a stylesheet; the site builder asks for that separately. There
is no client-side highlighter.
"""

# Pygments publishes no type information. Keep the gaps in this module.
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexer import Lexer
from pygments.lexers import ClassNotFound, TextLexer, get_lexer_by_name


def highlighted_html(source: str, language: str) -> str:
    """ Return Pygments HTML for one fence body, without a wrapper. """
    rendered = highlight(source, _lexer(language), _formatter(nowrap=True))
    return str(rendered)


def pygments_stylesheet() -> str:
    """ Return CSS for the classes ``highlighted_html`` emits. """
    styles = _formatter(nowrap=False).get_style_defs(".highlight")
    return str(styles)


def _formatter(*, nowrap: bool) -> HtmlFormatter[str]:
    return HtmlFormatter(nowrap=nowrap, nobackground=True)


def _lexer(language: str) -> Lexer:
    if language == "":
        return TextLexer()
    try:
        return get_lexer_by_name(language)
    except ClassNotFound:
        return TextLexer()
