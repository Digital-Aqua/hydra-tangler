""" Load outputs from the ``hydra_tangler.outputs`` entry point.

Built-ins register through the same group as third-party outputs.
Call ``load_outputs`` or ``select_outputs``; importing the package
does not render a book.
"""

from collections.abc import Sequence
from importlib.metadata import EntryPoint, entry_points
from pathlib import Path
from typing import cast

from hydra_tangler.model import UnsafeOutputPath
from hydra_tangler.outputs.base import Output

_GROUP = "hydra_tangler.outputs"


class OutputLoadError(Exception):
    """ An entry point did not provide an output. """


class UnknownOutput(Exception):
    """ The requested output name is not registered. """

    name: str

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown output: {name}")


def load_outputs() -> tuple[Output, ...]:
    """ Return the registered outputs, sorted by entry-point name. """
    points = entry_points(group=_GROUP)
    loaded: list[Output] = []
    for point in sorted(points, key=lambda item: item.name):
        output = _load(point)
        if not isinstance(output, Output):
            raise OutputLoadError(f"{point.name} is not an output")
        check_mount(output.mount)
        loaded.append(output)
    return tuple(loaded)


def check_mount(mount: Path) -> None:
    """ Raise ``OutputLoadError`` when ``mount`` leaves the target. """
    try:
        # Local import: mounting imports this package's base types.
        from hydra_tangler.mounting import require_mount

        require_mount(mount)
    except UnsafeOutputPath as err:
        raise OutputLoadError(
            f"output mount escapes the target: {err.raw!r}"
        ) from None


def _load(point: EntryPoint) -> object:
    return cast(object, point.load())


def select_outputs(requested: Sequence[str] = ()) -> tuple[Output, ...]:
    """ Pick the named outputs, or every registered output.

    ``requested`` is the repeated ``--output`` option. An empty
    sequence runs every output.
    """
    available = load_outputs()
    if not requested:
        return available
    return tuple(_one(available, name) for name in requested)


def _one(available: tuple[Output, ...], name: str) -> Output:
    for output in available:
        if output.name == name:
            return output
    raise UnknownOutput(name)
