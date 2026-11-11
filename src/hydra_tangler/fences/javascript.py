""" JavaScript fences.

Tags ``javascript`` and ``js``. Headers use a line comment. This
module does not parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Javascript(PlainText):
    """ JavaScript fences, commented with ``// ``. """

    tags: ClassVar[tuple[str, ...]] = ("javascript", "js")
    comment_prefix: ClassVar[str] = "// "
