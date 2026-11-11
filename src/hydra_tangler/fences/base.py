""" Shared fence results and the path check every fence class uses.

A fence class claims one fence. It does not read the book and does
not write files. Path containment is ``vet_output_path``; this module
turns a rejection into a diagnostic at the fence's opening line.
"""

from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.model import Diagnostic, Fence, RejectedPath, vet_output_path


@dataclass(frozen=True)
class HeaderStyle:
    """ Comment wrapping and placement for one fence's header.

    ``prefix`` and ``suffix`` wrap the generated line. ``after_doctype``
    places that line after a leading ``<!doctype`` line. The header
    text is not stored here: it names every contributing source, which
    a single fence does not know.
    """

    prefix: str
    suffix: str
    after_doctype: bool


@dataclass(frozen=True)
class Emission:
    """ The lines one fence contributes to one output file.

    ``markdown_lines`` lines up with ``lines``. ``open_line`` is the
    fence's opening line, used when a generated header needs a source
    location. ``header`` is the resolved comment style, or None when
    this fence asks for no header.
    """

    path: Path
    lines: tuple[str, ...]
    markdown_path: Path
    markdown_lines: tuple[int, ...]
    open_line: int
    header: HeaderStyle | None


@dataclass(frozen=True)
class Claim:
    """ The outcome of a fence class accepting a fence.

    A claim may carry lines, a diagnostic, or both. A bad path carries
    only a diagnostic, so nothing is emitted for that fence.
    """

    emission: Emission | None = None
    diagnostic: Diagnostic | None = None


def output_path(raw: str) -> Path | None:
    """ Return a normalized relative path, or None when it is refused. """
    verdict = vet_output_path(raw)
    if isinstance(verdict, RejectedPath):
        return None
    return verdict.path


def path_diagnostic(fence: Fence, raw: str) -> Diagnostic:
    """ An error for a ``file`` value that is not a safe relative path.

    Escapes use ``path-escapes-target``. An empty path, a control
    character, or one of ``< > : " | ? *`` uses ``bad-path``. The line
    is the fence's opening line.
    """
    verdict = vet_output_path(raw)
    escapes = isinstance(verdict, RejectedPath) and verdict.escapes
    if escapes:
        return Diagnostic(
            fence.path,
            fence.open_line,
            "error",
            "path-escapes-target",
            f"file path escapes the target: {raw}",
        )
    return Diagnostic(
        fence.path,
        fence.open_line,
        "error",
        "bad-path",
        f"bad file path: {raw}",
    )
