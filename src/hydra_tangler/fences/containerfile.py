""" Containerfile fences.

Tags ``containerfile`` and ``dockerfile``. Comment style stays the
plaintext default. This module does not parse Markdown and does not
write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Containerfile(PlainText):
    """ Containerfile and Dockerfile fences. """

    tags: ClassVar[tuple[str, ...]] = ("containerfile", "dockerfile")
