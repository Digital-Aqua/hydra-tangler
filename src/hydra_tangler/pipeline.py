""" Load a book and render the selected outputs.

``build_book`` is the shared front door for the tangle command, the
check and watch commands, and the language server. Link checking
and lint are separate steps: this module does not run them, and it
does not decide process exit codes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.book import load_book
from hydra_tangler.model import (
    Book,
    Diagnostic,
    FileSet,
    UnsafeOutputPath,
)
from hydra_tangler.mounting import (
    assemble_output,
    collision_diagnostics,
    require_mount,
)
from hydra_tangler.outputs import select_outputs
from hydra_tangler.outputs.base import Output, Rendered, RenderedOutput
from hydra_tangler.sourcemap import SourceMap
from hydra_tangler.writer import write_files


@dataclass(frozen=True)
class BuildResult:
    """ A book, the outputs rendered from it, and their diagnostics.

    ``diagnostics`` covers reading and rendering only. Dead links and
    lint findings are added by the caller.
    """

    book: Book
    outputs: tuple[RenderedOutput, ...]
    diagnostics: tuple[Diagnostic, ...]


def build_book(
    root: Path,
    source: Path | None = None,
    outputs: Sequence[str] = (),
    *,
    overrides: Mapping[Path, str] | None = None,
    target: Path | None = None,
) -> BuildResult:
    """ Load the book under ``source`` and render the named outputs.

    ``source`` defaults to ``root`` (the working directory, or the
    language server's workspace root). ``outputs`` limits rendering
    to those registered names; an empty sequence runs every output.
    ``overrides`` is forwarded to ``load_book``. ``target`` is skipped
    while discovering Markdown when it sits inside the source.
    """
    directory = source_directory(root, source)
    book = load_book(directory, overrides=overrides, target=target)
    rendered = render_outputs(book, select_outputs(outputs))
    diagnostics = (
        *build_diagnostics(book, rendered),
        *collision_diagnostics(rendered),
    )
    return BuildResult(book, rendered, diagnostics)


def render_outputs(
    book: Book,
    outputs: Sequence[Output],
) -> tuple[RenderedOutput, ...]:
    """ Render each output. The order follows ``outputs``.

    An output whose files use a path outside the target becomes an
    error diagnostic when the book has one document to attach it to.
    Otherwise ``UnsafeOutputPath`` propagates for the caller to print
    as ``error:`` without a traceback.
    """
    return tuple(_render_one(book, item) for item in outputs)


def _render_one(book: Book, item: Output) -> RenderedOutput:
    require_mount(item.mount)
    try:
        rendered = item.render(book)
    except UnsafeOutputPath as err:
        return _escaped(book, item, err)
    return RenderedOutput(item.name, item.mount, rendered)


def _escaped(book: Book, item: Output, err: UnsafeOutputPath) -> RenderedOutput:
    diagnostic = _escape_diagnostic(book, err)
    if diagnostic is None:
        raise err
    rendered = Rendered(FileSet(), SourceMap(), (diagnostic,))
    return RenderedOutput(item.name, item.mount, rendered)


def _escape_diagnostic(book: Book, err: UnsafeOutputPath) -> Diagnostic | None:
    """ Attach the refusal to the only document, when there is one. """
    if len(book.documents) != 1:
        return None
    return Diagnostic(
        book.documents[0].path,
        1,
        "error",
        "path-escapes-target",
        str(err),
    )


def build_diagnostics(
    book: Book,
    rendered: Sequence[RenderedOutput],
) -> tuple[Diagnostic, ...]:
    """ Book diagnostics followed by each output's diagnostics. """
    found = list(book.diagnostics)
    for item in rendered:
        found.extend(item.rendered.diagnostics)
    return tuple(found)


def write_rendered(
    result: BuildResult,
    root: Path,
    target: Path | None,
    *,
    sourcemap: bool = True,
) -> Path:
    """ Write every output into one directory and return that directory.

    Paths are prefixed with each output's mount. ``sourcemap`` adds
    ``sourcemap.json`` to the same write.
    """
    directory = target_directory(target, root)
    file_set = assemble_output(result.outputs, sourcemap=sourcemap)
    write_files(file_set, directory)
    return directory


def source_directory(root: Path, source: Path | None) -> Path:
    """ The Markdown directory: ``source``, or ``root`` when omitted. """
    if source is not None:
        return source
    return root


def target_directory(explicit: Path | None, root: Path) -> Path:
    """ The single directory every output is written into.

    ``explicit`` is that directory. When it is omitted, the directory
    is ``root / "_build"``.
    """
    if explicit is None:
        return root / "_build"
    return explicit
