""" Claim ``file=test:<path>`` fences.

The path after ``test:`` is placed under the ``tests/`` output root,
separate from a code file of the same name. Other fences are declined.
This module does not write the tests directory.
"""

from pathlib import Path

from hydra_tangler.fences.base import (
    Claim,
    bad_path,
    emission_for,
    output_path,
)
from hydra_tangler.model import Fence

_PREFIX = "test:"
_ROOT = Path("tests")


class TestFence:
    """ Handles ``file=test:<path>`` fences. """

    def claim(self, fence: Fence) -> Claim | None:
        """ Claim a test path and root it at ``tests/``. """
        raw = fence.attrs.get("file")
        if raw is None or not raw.startswith(_PREFIX):
            return None
        inner = raw[len(_PREFIX) :]
        relative = output_path(inner)
        if relative is None:
            return Claim(diagnostic=bad_path(fence, raw))
        return Claim(emission=emission_for(fence, _ROOT / relative))


handler = TestFence()
