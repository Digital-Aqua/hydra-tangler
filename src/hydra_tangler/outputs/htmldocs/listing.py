""" Group tangled fences for the files page.

Every fence with a ``file`` attribute is listed under that output
path. Links point at the fence anchor on the document page. This
module does not decide whether the path exists on disk.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.model import Book, Fence
from hydra_tangler.outputs.htmldocs.context import FileGroup, Neighbour
from hydra_tangler.outputs.htmldocs.render import fence_anchor
from hydra_tangler.outputs.htmldocs.urls import anchored, html_path


def file_groups(book: Book, origin: Path) -> tuple[FileGroup, ...]:
    """ Return tangled paths in alphabetical order, as seen from ``origin``. """
    spots = _spots(book, origin)
    names = sorted({spot.path for spot in spots})
    return tuple(_group(name, spots) for name in names)


@dataclass(frozen=True)
class _Spot:
    """ One contributing fence, already linked from the files page. """

    path: str
    label: str
    href: str


def _spots(book: Book, origin: Path) -> tuple[_Spot, ...]:
    found: list[_Spot] = []
    for document in book.documents:
        for fence in document.fences:
            spot = _spot(document.path, fence, origin)
            if spot is not None:
                found.append(spot)
    return tuple(found)


def _spot(source: Path, fence: Fence, origin: Path) -> _Spot | None:
    output_path = fence.attrs.get("file", "")
    if output_path == "":
        return None
    anchor = fence_anchor(source, fence.open_line)
    href = anchored(origin, html_path(source), anchor)
    label = f"{source.as_posix()}:{fence.open_line}"
    return _Spot(output_path, label, href)


def _group(path: str, spots: Sequence[_Spot]) -> FileGroup:
    sources = tuple(
        Neighbour(spot.label, spot.href) for spot in spots if spot.path == path
    )
    return FileGroup(path, sources)
