""" YAML fences.

Tags ``yaml`` and ``yml``. Comment style stays the plaintext default.
This module does not parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Yaml(PlainText):
    """ YAML and ``yml`` fences. """

    tags: ClassVar[tuple[str, ...]] = ("yaml", "yml")
