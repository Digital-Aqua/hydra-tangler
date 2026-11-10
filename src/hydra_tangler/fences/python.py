""" Claim ``file=<path>`` fences and describe comment headers.

The path's extension chooses the comment syntax, not the fence's
language tag, so a ``css`` fence writing ``web.css`` and a ``python``
fence writing the same file agree. ``file=test:...`` is left for the
pytest handler. This module does not concatenate fences or write files.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.fences.base import (
    Claim,
    bad_path,
    emission_for,
    output_path,
)
from hydra_tangler.model import Fence

_TEST_PREFIX = "test:"
_HASH = frozenset({".py", ".yaml", ".yml", ".toml"})


@dataclass(frozen=True)
class CommentStyle:
    """ The prefix and suffix that wrap a generated-file header. """

    prefix: str
    suffix: str


class FileFence:
    """ Handles ``file=`` fences for ordinary output paths. """

    def claim(self, fence: Fence) -> Claim | None:
        """ Claim ``file=`` values other than ``test:``. """
        raw = fence.attrs.get("file")
        if raw is None or raw.startswith(_TEST_PREFIX):
            return None
        relative = output_path(raw)
        if relative is None:
            return Claim(diagnostic=bad_path(fence, raw))
        return Claim(emission=emission_for(fence, relative))


def comment_style(path: Path) -> CommentStyle | None:
    """ Return the comment syntax for ``path``, or None if unknown. """
    if path.name == "Containerfile" or path.suffix.lower() in _HASH:
        return CommentStyle("# ", "")
    if path.suffix.lower() == ".css":
        return CommentStyle("/* ", " */")
    if path.suffix.lower() == ".js":
        return CommentStyle("// ", "")
    if path.suffix.lower() == ".html":
        return CommentStyle("<!-- ", " -->")
    return None


def generated_header(path: Path, sources: Sequence[Path]) -> str | None:
    """ Return the ``GENERATED from ...`` line, or None if no comment. """
    style = comment_style(path)
    if style is None:
        return None
    shown = ", ".join(source.as_posix() for source in sources)
    body = f"GENERATED from {shown} - do not edit"
    return f"{style.prefix}{body}{style.suffix}"


def header_line_index(path: Path, body: Sequence[str]) -> int:
    """ Where the header goes. HTML keeps a leading doctype first. """
    if path.suffix.lower() != ".html" or not body:
        return 0
    if body[0].lstrip().lower().startswith("<!doctype"):
        return 1
    return 0


handler = FileFence()
