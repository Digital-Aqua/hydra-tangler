""" The checker interface shared by basedpyright and ruff.

A checker builds its argv and parses its own JSON. Running the
process is someone else's job.
"""

from pathlib import Path
from typing import Protocol

from hydra_tangler.check.reported import Reported


class Checker(Protocol):
    """ One lint tool. """

    name: str

    def argv(
        self,
        project: Path,
        configured: tuple[str, ...],
    ) -> tuple[str, ...]:
        """ Return the command without the files to check. """
        raise NotImplementedError

    def read(self, stdout: str) -> tuple[Reported, ...]:
        """ Parse the checker's JSON stdout. """
        raise NotImplementedError
