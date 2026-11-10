""" Load outputs from the ``hydra_tangler.outputs`` entry point.

Built-ins register through the same group as third-party outputs.
Call ``load_outputs`` or ``select_outputs``; importing the package
does not render a book.
"""

from importlib.metadata import EntryPoint, entry_points
from typing import cast

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
        loaded.append(output)
    return tuple(loaded)


def _load(point: EntryPoint) -> object:
    return cast(object, point.load())


def select_outputs(
    requested: str | None,
    configured: tuple[str, ...],
) -> tuple[Output, ...]:
    """ Pick outputs by CLI name, else config, else every output.

    ``requested`` is the ``--output`` value. ``configured`` is the
    ``[tool.hydra] outputs`` list, ignored when ``requested`` is set.
    """
    available = load_outputs()
    if requested is not None:
        return (_one(available, requested),)
    if not configured:
        return available
    return tuple(_one(available, name) for name in configured)


def _one(available: tuple[Output, ...], name: str) -> Output:
    for output in available:
        if output.name == name:
            return output
    raise UnknownOutput(name)
