""" Load fence handlers from the ``hydra_tangler.fences`` entry point.

Built-in handlers are registered the same way as third-party ones.
Importing this package does not load the handlers; call
``load_handlers`` when a book is tangled. This package does not
decide output filenames beyond what each handler claims.
"""

from importlib.metadata import EntryPoint, entry_points
from typing import cast

from hydra_tangler.fences.base import FenceHandler

_GROUP = "hydra_tangler.fences"


class FenceLoadError(Exception):
    """ An entry point did not provide a fence handler. """


def load_handlers() -> tuple[FenceHandler, ...]:
    """ Return the registered handlers, sorted by entry-point name. """
    points = entry_points(group=_GROUP)
    loaded: list[FenceHandler] = []
    for point in sorted(points, key=lambda item: item.name):
        handler = _load(point)
        if not isinstance(handler, FenceHandler):
            raise FenceLoadError(
                f"{point.name} is not a fence handler"
            )
        loaded.append(handler)
    return tuple(loaded)


def _load(point: EntryPoint) -> object:
    return cast(object, point.load())
