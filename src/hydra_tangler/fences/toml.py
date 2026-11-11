""" TOML fences.

The tag is ``toml``. Comment style stays the plaintext default.
This module does not parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Toml(PlainText):
    """ TOML fences. """

    tags: ClassVar[tuple[str, ...]] = ("toml",)
