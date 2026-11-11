""" The checker interface shared by basedpyright and ruff.

A checker builds its argv and parses its own JSON. Running the
process is someone else's job. Commands come from the caller, not
from a project file.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from hydra_tangler.check.reported import Reported


@dataclass(frozen=True)
class CheckerCommands:
    """ Argv prefixes for the checkers.

    An empty command means that checker builds its default
    ``uv run --project <root>`` invocation.
    """

    pyright: tuple[str, ...] = ()
    ruff: tuple[str, ...] = ()


class Checker(Protocol):
    """ One lint tool. """

    name: str

    def configured(self, commands: CheckerCommands) -> tuple[str, ...]:
        """ The argv prefix this checker should use. """
        raise NotImplementedError

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
