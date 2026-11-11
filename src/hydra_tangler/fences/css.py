""" CSS fences.

The tag is ``css``. Headers use a block comment. This module does not
parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Css(PlainText):
    """ CSS fences, commented with ``/* `` ... `` */``. """

    tags: ClassVar[tuple[str, ...]] = ("css",)
    comment_prefix: ClassVar[str] = "/* "
    comment_suffix: ClassVar[str] = " */"
