""" Tangled code: every claimed fence, concatenated in book order.

Fences that name the same path are joined in document order, then
fence order. A comment header names the Markdown files that
contributed. The header's source-map line is the first fence's
opening line. This module returns a FileSet and does not write it.
"""

from collections.abc import Sequence
from pathlib import Path

from hydra_tangler.fences import load_handlers
from hydra_tangler.fences.base import Claim, Emission, FenceHandler
from hydra_tangler.fences.python import generated_header, header_line_index
from hydra_tangler.model import (
    Book,
    Diagnostic,
    Fence,
    FileSet,
    OutputFile,
)
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
)


class PythonOutput:
    """ The ``python`` output: all tangled code and test files. """

    name: str = "python"

    def render(self, book: Book) -> Rendered:
        """ Claim fences and concatenate them into output files. """
        collected = _collect(book, load_handlers())
        files: list[OutputFile] = []
        records: list[SourceRecord] = []
        problems = list(collected.diagnostics)
        for path, emissions in _by_path(collected.emissions):
            built = _assemble(path, emissions)
            if isinstance(built, Diagnostic):
                problems.append(built)
                continue
            text, assembled = built
            files.append(OutputFile(path, text.encode("utf-8")))
            records.extend(_records(path, assembled))
        return Rendered(
            FileSet(tuple(files)),
            SourceMap(tuple(records)),
            tuple(problems),
        )


class _Collected:
    """ Emissions and diagnostics gathered from one book. """

    def __init__(self) -> None:
        self.emissions: list[Emission] = []
        self.diagnostics: list[Diagnostic] = []


def _collect(book: Book, handlers: Sequence[FenceHandler]) -> _Collected:
    found = _Collected()
    for document in book.documents:
        for fence in document.fences:
            claim = _claim(fence, handlers)
            if claim is None:
                continue
            _keep(found, claim)
    return found


def _keep(found: _Collected, claim: Claim) -> None:
    if claim.diagnostic is not None:
        found.diagnostics.append(claim.diagnostic)
    if claim.emission is not None:
        found.emissions.append(claim.emission)


def _claim(fence: Fence, handlers: Sequence[FenceHandler]) -> Claim | None:
    for handler in handlers:
        claim = handler.claim(fence)
        if claim is not None:
            return claim
    return None


def _by_path(
    emissions: Sequence[Emission],
) -> tuple[tuple[Path, tuple[Emission, ...]], ...]:
    order: list[Path] = []
    grouped: dict[Path, list[Emission]] = {}
    for emission in emissions:
        bucket = grouped.get(emission.path)
        if bucket is None:
            order.append(emission.path)
            grouped[emission.path] = [emission]
            continue
        bucket.append(emission)
    return tuple((path, tuple(grouped[path])) for path in order)


def _assemble(
    path: Path,
    emissions: Sequence[Emission],
) -> tuple[str, tuple[tuple[str, Path, int], ...]] | Diagnostic:
    body, origins = _body(emissions)
    header = generated_header(path, _sources(emissions))
    if header is None:
        return _no_comment(path, emissions[0])
    index = header_line_index(path, body)
    origin = (emissions[0].markdown_path, emissions[0].open_line)
    lines = list(body)
    located = list(origins)
    lines.insert(index, header)
    located.insert(index, origin)
    text = "\n".join(lines) + "\n"
    return text, tuple(
        (line, markdown, number)
        for line, (markdown, number) in zip(lines, located, strict=True)
    )


def _body(
    emissions: Sequence[Emission],
) -> tuple[list[str], list[tuple[Path, int]]]:
    lines: list[str] = []
    origins: list[tuple[Path, int]] = []
    for emission in emissions:
        for line, number in zip(
            emission.lines, emission.markdown_lines, strict=True
        ):
            lines.append(line)
            origins.append((emission.markdown_path, number))
    return lines, origins


def _sources(emissions: Sequence[Emission]) -> tuple[Path, ...]:
    seen: list[Path] = []
    for emission in emissions:
        if emission.markdown_path not in seen:
            seen.append(emission.markdown_path)
    return tuple(seen)


def _no_comment(path: Path, emission: Emission) -> Diagnostic:
    return Diagnostic(
        emission.markdown_path,
        emission.open_line,
        "error",
        "no-comment",
        f"no comment syntax for output file: {path.as_posix()}",
    )


def _records(
    path: Path,
    assembled: Sequence[tuple[str, Path, int]],
) -> tuple[SourceRecord, ...]:
    return tuple(
        SourceRecord(
            OutputSite(path, number),
            MarkdownSite(markdown, markdown_line),
        )
        for number, (_, markdown, markdown_line) in enumerate(
            assembled, start=1
        )
    )


output = PythonOutput()
