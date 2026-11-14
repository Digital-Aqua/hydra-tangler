""" The base fence class: a ``file=`` path and a hash comment.

Subclasses change tags, comment markers, and ``exclusions``. They do
not parse the info string and do not write files. Per-fence attributes
override the class defaults: ``comment``, ``comment_end``, and
``header=false``.
"""

from pathlib import Path
from typing import ClassVar

from hydra_tangler.fences.base import (
    Claim,
    Emission,
    HeaderStyle,
    output_path,
    path_diagnostic,
)
from hydra_tangler.fences.exemptions import Exclusion
from hydra_tangler.model import Fence

_FALSE = "false"


class PlainText:
    """ Claim ``file=`` fences and resolve their header style.

    The default comment is a hash. ``header_after_doctype`` is off:
    the header is the first line of the output file. ``exclusions``
    is empty; a language subclass lists rules its fragments are not
    expected to satisfy.
    """

    tags: ClassVar[tuple[str, ...]] = ("text", "txt", "plaintext")
    comment_prefix: ClassVar[str] = "# "
    comment_suffix: ClassVar[str] = ""
    header_after_doctype: ClassVar[bool] = False
    exclusions: ClassVar[tuple[Exclusion, ...]] = ()

    def claim(self, fence: Fence) -> Claim:
        """ Validate ``file=`` and return the emission for this fence. """
        raw = fence.attrs.get("file", "")
        relative = output_path(raw)
        if relative is None:
            return Claim(diagnostic=path_diagnostic(fence, raw))
        return Claim(emission=_emission(self, fence, relative))


def _emission(handler: PlainText, fence: Fence, path: Path) -> Emission:
    numbers = tuple(
        fence.body_line + index for index in range(len(fence.body_lines))
    )
    return Emission(
        path,
        fence.body_lines,
        fence.path,
        numbers,
        fence.open_line,
        _style(handler, fence),
    )


def _style(handler: PlainText, fence: Fence) -> HeaderStyle | None:
    if fence.attrs.get("header", "").lower() == _FALSE:
        return None
    return HeaderStyle(
        fence.attrs.get("comment", handler.comment_prefix),
        fence.attrs.get("comment_end", handler.comment_suffix),
        handler.header_after_doctype,
    )
