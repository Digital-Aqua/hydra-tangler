""" The output interface: a Book becomes files and a source map.

An output does not touch the output directory. The writer does that.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from hydra_tangler.model import Book, Diagnostic, FileSet
from hydra_tangler.sourcemap import SourceMap


@dataclass(frozen=True)
class Rendered:
    """ One output's files, source map, and diagnostics. """

    files: FileSet
    source_map: SourceMap
    diagnostics: tuple[Diagnostic, ...] = ()


@runtime_checkable
class Output(Protocol):
    """ Builds a FileSet from a book. """

    name: str

    def render(self, book: Book) -> Rendered:
        """ Return the files this output wants written. """
        raise NotImplementedError
