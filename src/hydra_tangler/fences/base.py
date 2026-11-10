""" What a fence handler is, and the path rules every handler shares.

A handler looks at one fence and either claims it or declines it.
Handlers do not read the book and do not write files.
"""

import posixpath
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from hydra_tangler.model import Diagnostic, Fence


@dataclass(frozen=True)
class Emission:
    """ The lines one fence contributes to one output file.

    ``markdown_lines`` lines up with ``lines``. ``open_line`` is the
    fence's opening line, used when a generated header needs a source
    location.
    """

    path: Path
    lines: tuple[str, ...]
    markdown_path: Path
    markdown_lines: tuple[int, ...]
    open_line: int


@dataclass(frozen=True)
class Claim:
    """ The outcome of a handler accepting a fence.

    A claim may carry lines, a diagnostic, or both. A bad path carries
    only a diagnostic, so nothing is emitted for that fence.
    """

    emission: Emission | None = None
    diagnostic: Diagnostic | None = None


@runtime_checkable
class FenceHandler(Protocol):
    """ Decides whether a fence contributes to an output file. """

    def claim(self, fence: Fence) -> Claim | None:
        """ Return None when this handler does not apply to ``fence``. """


def output_path(raw: str) -> Path | None:
    """ Return a relative output path, or None if ``raw`` escapes it.

    Absolute paths, ``.``, and anything that normalizes to ``..`` are
    rejected. The check uses POSIX rules because fence paths are
    written with forward slashes.
    """
    if not raw or raw.startswith("/"):
        return None
    normalized = posixpath.normpath(raw)
    if normalized in (".", "..") or normalized.startswith("../"):
        return None
    if normalized.startswith("/"):
        return None
    return Path(normalized)


def emission_for(fence: Fence, path: Path) -> Emission:
    """ Build an emission from a fence body, keeping line numbers. """
    numbers = tuple(
        fence.body_line + index for index in range(len(fence.body_lines))
    )
    return Emission(
        path,
        fence.body_lines,
        fence.path,
        numbers,
        fence.open_line,
    )


def bad_path(fence: Fence, raw: str) -> Diagnostic:
    """ A diagnostic for a ``file`` value that is not a safe path. """
    return Diagnostic(
        fence.path,
        fence.open_line,
        "error",
        "bad-path",
        f"bad file path: {raw}",
    )
