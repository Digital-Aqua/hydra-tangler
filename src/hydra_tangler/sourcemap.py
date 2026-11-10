""" Map output lines to the Markdown lines that produced them.

A map is pure data built by an output. It is not written to the
output directory. Look up an output line to find the Markdown site,
or a Markdown line to find the output sites it produced.
"""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MarkdownSite:
    """ A line in a source document. """

    path: Path
    line: int


@dataclass(frozen=True)
class OutputSite:
    """ A line in a tangled file. """

    path: Path
    line: int


@dataclass(frozen=True)
class SourceRecord:
    """ One output line and the Markdown line it came from. """

    output: OutputSite
    markdown: MarkdownSite


@dataclass(frozen=True)
class SourceMap:
    """ The records for every file in one output. """

    records: tuple[SourceRecord, ...] = ()

    def markdown_at(self, path: Path, line: int) -> MarkdownSite | None:
        """ Return the Markdown site that produced ``path:line``. """
        for record in self.records:
            if record.output.path == path and record.output.line == line:
                return record.markdown
        return None

    def output_at(self, path: Path, line: int) -> tuple[OutputSite, ...]:
        """ Return output sites produced by this Markdown line. """
        return tuple(
            record.output
            for record in self.records
            if record.markdown.path == path and record.markdown.line == line
        )
