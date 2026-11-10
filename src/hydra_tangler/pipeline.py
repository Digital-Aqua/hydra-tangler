""" Load a book and render the selected outputs.

``build_book`` is the shared front door for the tangle command, the
check and watch commands, and the language server. Link checking
and lint are separate steps: this module does not run them, and it
does not decide process exit codes.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.book import default_source, load_book
from hydra_tangler.config import HydraConfig, load_config
from hydra_tangler.model import Book, Diagnostic
from hydra_tangler.outputs import select_outputs
from hydra_tangler.outputs.base import Output, Rendered
from hydra_tangler.writer import write_files


@dataclass(frozen=True)
class RenderedOutput:
    """ One output's name and the files it produced. """

    name: str
    rendered: Rendered


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
    output: str | None = None,
    *,
    overrides: Mapping[Path, str] | None = None,
) -> BuildResult:
    """ Read ``root``'s config, load the book, and render outputs.

    ``source`` overrides the config and the default source directory.
    ``output`` limits rendering to one registered output name.
    ``overrides`` is forwarded to ``load_book``: paths are relative to
    the source directory, and unsaved text replaces the file on disk.
    """
    config = load_config(root)
    directory = source_directory(root, source, config)
    book = load_book(directory, overrides=overrides)
    rendered = render_outputs(book, select_outputs(output, config.outputs))
    return BuildResult(book, rendered, build_diagnostics(book, rendered))


def render_outputs(
    book: Book,
    outputs: Sequence[Output],
) -> tuple[RenderedOutput, ...]:
    """ Render each output. The order follows ``outputs``. """
    return tuple(
        RenderedOutput(item.name, item.render(book)) for item in outputs
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
) -> tuple[Path, ...]:
    """ Write each rendered output and return the directories used. """
    count = len(result.outputs)
    written: list[Path] = []
    for item in result.outputs:
        directory = target_directory(item.name, target, root, count)
        write_files(item.rendered.files, directory)
        written.append(directory)
    return tuple(written)


def source_directory(
    root: Path,
    source: Path | None,
    config: HydraConfig,
) -> Path:
    """ Resolve the Markdown directory for this project. """
    if source is not None:
        return source
    if config.source is not None:
        return root / config.source
    return default_source(root)


def target_directory(
    name: str,
    explicit: Path | None,
    root: Path,
    count: int,
) -> Path:
    """ Where one output is written.

    A single output uses ``explicit`` as given. Several outputs each
    get a subdirectory so they do not overwrite one another.
    """
    if explicit is None:
        return root / "_build" / name
    if count == 1:
        return explicit
    return explicit / name
