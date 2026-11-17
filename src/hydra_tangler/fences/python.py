""" Python fences.

Tags ``python`` and ``py``. Comment style stays the plaintext default.
Checker defaults, including import sorting, live in
``check/defaults.py``. This module does not parse Markdown and does
not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.plaintext import PlainText


class Python(PlainText):
    """ Python and ``py`` fences. """

    tags: ClassVar[tuple[str, ...]] = ("python", "py")
