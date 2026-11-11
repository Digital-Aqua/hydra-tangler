""" The output interface: a Book becomes files and a source map.

An output does not touch the output directory and does not know where
it is mounted. The pipeline prefixes paths with ``mount`` and the
writer creates the files.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from hydra_tangler.model import Book, Diagnostic, FileSet
from hydra_tangler.sourcemap import SourceMap


@dataclass(frozen=True)
class Rendered:
    """ One output's files, source map, and diagnostics. """

    files: FileSet
    source_map: SourceMap
    diagnostics: tuple[Diagnostic, ...] = ()


@dataclass(frozen=True)
class RenderedOutput:
    """ One output's name, mount, and what ``render`` returned. """

    name: str
    mount: Path
    rendered: Rendered


@runtime_checkable
class Output(Protocol):
    """ Builds a FileSet from a book.

    ``mount`` is the path prefix the pipeline applies. ``.`` means
    the output's paths are already target-relative.
    """

    name: str
    mount: Path

    def render(self, book: Book) -> Rendered:
        """ Return the files this output wants written. """
        raise NotImplementedError
