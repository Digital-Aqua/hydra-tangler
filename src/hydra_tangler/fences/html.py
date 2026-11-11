""" HTML fences.

The tag is ``html``. Headers use an HTML comment and follow a leading
doctype. This module does not parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Html(PlainText):
    """ HTML fences. The header follows a leading doctype. """

    tags: ClassVar[tuple[str, ...]] = ("html",)
    comment_prefix: ClassVar[str] = "<!-- "
    comment_suffix: ClassVar[str] = " -->"
    header_after_doctype: ClassVar[bool] = True
