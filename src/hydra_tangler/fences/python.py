""" Python fences.

Tags ``python`` and ``py``. Comment style stays the plaintext default.
Ruff ``I001`` is excluded because a fence is a fragment: its import
block is not a section the author is expected to sort. This module
does not parse Markdown and does not write files.
"""

from typing import ClassVar

from hydra_tangler.fences.exemptions import Exclusion
from hydra_tangler.fences.plaintext import PlainText


class Python(PlainText):
    """ Python and ``py`` fences. """

    tags: ClassVar[tuple[str, ...]] = ("python", "py")
    exclusions: ClassVar[tuple[Exclusion, ...]] = (
        Exclusion("ruff", ("I001",)),
    )
