""" Load fence classes from the ``hydra_tangler.fences`` entry point.

Each entry point names a ``PlainText`` subclass. The registry maps
every tag to one instance. Importing this package does not load the
entry points; call ``load_fences`` when a book is tangled. This
package does not write files.
"""

from collections.abc import Mapping, Sequence
from importlib.metadata import EntryPoint, entry_points
from types import MappingProxyType
from typing import cast

from hydra_tangler.fences.dispatch import claim_fence
from hydra_tangler.fences.plaintext import PlainText

_GROUP = "hydra_tangler.fences"

__all__ = ["FenceLoadError", "claim_fence", "load_fences", "registry_from"]


class FenceLoadError(Exception):
    """ An entry point did not provide a fence class, or a tag collided. """


def load_fences() -> Mapping[str, PlainText]:
    """ Return the tag-to-class map from the fence entry-point group. """
    points = entry_points(group=_GROUP)
    classes = tuple(
        _load(point) for point in sorted(points, key=lambda item: item.name)
    )
    return registry_from(classes)


def registry_from(
    classes: Sequence[type[PlainText]],
) -> Mapping[str, PlainText]:
    """ Map each tag to one instance. A repeated tag is a load error. """
    found: dict[str, PlainText] = {}
    owners: dict[str, str] = {}
    for cls in classes:
        _register(cls, found, owners)
    return MappingProxyType(found)


def _register(
    cls: type[PlainText],
    found: dict[str, PlainText],
    owners: dict[str, str],
) -> None:
    instance = cls()
    for tag in cls.tags:
        previous = owners.get(tag)
        if previous is not None:
            message = (
                f"fence tag {tag!r} is registered by both "
                + f"{previous} and {cls.__name__}"
            )
            raise FenceLoadError(message)
        owners[tag] = cls.__name__
        found[tag] = instance


def _load(point: EntryPoint) -> type[PlainText]:
    loaded = cast(object, point.load())
    if isinstance(loaded, type) and issubclass(loaded, PlainText):
        return loaded
    raise FenceLoadError(f"{point.value} is not a PlainText fence class")
