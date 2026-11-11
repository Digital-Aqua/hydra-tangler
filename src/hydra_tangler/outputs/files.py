""" Concatenate claimed fences into output files.

Fences that name the same path are joined in document order, then
fence order. The header text is built from the first fence's comment
style and the Markdown files that contributed. This module knows no
language: it does not import a fence class. It returns a FileSet and
does not write it.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.fences import claim_fence, load_fences
from hydra_tangler.fences.base import Claim, Emission, HeaderStyle
from hydra_tangler.fences.plaintext import PlainText
from hydra_tangler.model import Book, Diagnostic, FileSet, OutputFile
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
)

_DOCTYPE = "<!doctype"


class FilesOutput:
    """ The ``files`` output: every claimed fence, concatenated. """

    name: str = "files"
    mount: Path = Path(".")

    def render(self, book: Book) -> Rendered:
        """ Claim fences and concatenate them into output files. """
        collected = _collect(book, load_fences())
        files: list[OutputFile] = []
        records: list[SourceRecord] = []
        problems = list(collected.diagnostics)
        for group in _by_path(collected.emissions):
            problems.extend(_style_warning(group))
            built = _assemble(group)
            files.append(OutputFile(group.path, built.text.encode("utf-8")))
            records.extend(_records(group.path, built.lines))
        return Rendered(
            FileSet(tuple(files)),
            SourceMap(tuple(records)),
            tuple(problems),
        )


@dataclass(frozen=True)
class _Group:
    """ Emissions that share one output path, in book order. """

    path: Path
    emissions: tuple[Emission, ...]


@dataclass(frozen=True)
class _Line:
    """ One output line and the Markdown line it came from. """

    text: str
    markdown_path: Path
    markdown_line: int


@dataclass(frozen=True)
class _Assembled:
    """ The file text and the located lines it was built from. """

    text: str
    lines: tuple[_Line, ...]


class _Collected:
    """ Emissions and diagnostics gathered from one book. """

    def __init__(self) -> None:
        self.emissions: list[Emission] = []
        self.diagnostics: list[Diagnostic] = []


def _collect(book: Book, classes: Mapping[str, PlainText]) -> _Collected:
    found = _Collected()
    for document in book.documents:
        for fence in document.fences:
            claim = claim_fence(fence, classes)
            if claim is not None:
                _keep(found, claim)
    return found


def _keep(found: _Collected, claim: Claim) -> None:
    if claim.diagnostic is not None:
        found.diagnostics.append(claim.diagnostic)
    if claim.emission is not None:
        found.emissions.append(claim.emission)


def _by_path(emissions: Sequence[Emission]) -> tuple[_Group, ...]:
    order: list[Path] = []
    grouped: dict[Path, list[Emission]] = {}
    for emission in emissions:
        bucket = grouped.get(emission.path)
        if bucket is None:
            order.append(emission.path)
            grouped[emission.path] = [emission]
            continue
        bucket.append(emission)
    return tuple(_Group(path, tuple(grouped[path])) for path in order)


def _style_warning(group: _Group) -> tuple[Diagnostic, ...]:
    first = group.emissions[0].header
    for emission in group.emissions[1:]:
        if emission.header != first:
            return (_mixed(group.path, emission),)
    return ()


def _mixed(path: Path, emission: Emission) -> Diagnostic:
    return Diagnostic(
        emission.markdown_path,
        emission.open_line,
        "warning",
        "mixed-comment-styles",
        (
            f"mixed comment styles for {path.as_posix()}; "
            "keeping the first fence's header"
        ),
    )


def _assemble(group: _Group) -> _Assembled:
    lines = _body(group.emissions)
    style = group.emissions[0].header
    if style is None:
        return _joined(lines)
    header = _header_text(style, _sources(group.emissions))
    origin = _Line(
        header,
        group.emissions[0].markdown_path,
        group.emissions[0].open_line,
    )
    placed = list(lines)
    placed.insert(_index(style, lines), origin)
    return _joined(tuple(placed))


def _body(emissions: Sequence[Emission]) -> tuple[_Line, ...]:
    lines: list[_Line] = []
    for emission in emissions:
        for text, number in zip(
            emission.lines, emission.markdown_lines, strict=True
        ):
            lines.append(_Line(text, emission.markdown_path, number))
    return tuple(lines)


def _sources(emissions: Sequence[Emission]) -> tuple[Path, ...]:
    seen: list[Path] = []
    for emission in emissions:
        if emission.markdown_path not in seen:
            seen.append(emission.markdown_path)
    return tuple(seen)


def _header_text(style: HeaderStyle, sources: Sequence[Path]) -> str:
    shown = ", ".join(source.as_posix() for source in sources)
    return f"{style.prefix}GENERATED from {shown} - do not edit{style.suffix}"


def _index(style: HeaderStyle, lines: Sequence[_Line]) -> int:
    if not style.after_doctype or not lines:
        return 0
    if lines[0].text.lstrip().lower().startswith(_DOCTYPE):
        return 1
    return 0


def _joined(lines: Sequence[_Line]) -> _Assembled:
    text = "\n".join(line.text for line in lines) + "\n"
    return _Assembled(text, tuple(lines))


def _records(path: Path, lines: Sequence[_Line]) -> tuple[SourceRecord, ...]:
    return tuple(
        SourceRecord(
            OutputSite(path, number),
            MarkdownSite(line.markdown_path, line.markdown_line),
        )
        for number, line in enumerate(lines, start=1)
    )


output = FilesOutput()
