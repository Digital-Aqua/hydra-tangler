""" Command line: tangle, where, check, watch, and serve.

Document problems are printed as diagnostics. Error severity exits
1, without a traceback. Warning severity, including dead links, does
not. ``serve`` speaks the language server protocol on stdio and does
not print diagnostics.
"""

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from hydra_tangler.book import SourceMissing
from hydra_tangler.check.errors import LintError
from hydra_tangler.check.links import find_dead_links
from hydra_tangler.check.lint import lint_python
from hydra_tangler.config import ConfigError, load_config
from hydra_tangler.fences import FenceLoadError
from hydra_tangler.model import Diagnostic
from hydra_tangler.outputs import OutputLoadError, UnknownOutput, select_outputs
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.pipeline import (
    BuildResult,
    build_book,
    source_directory,
    target_directory,
    write_rendered,
)
from hydra_tangler.serve.server import run_stdio
from hydra_tangler.sourcemap import MarkdownSite, SourceMap
from hydra_tangler.watch import watch_markdown
from hydra_tangler.writer import WriterError

app = typer.Typer(add_completion=False, help="Tangle Markdown into code.")


class UsageError(Exception):
    """ The command line value is not a FILE:LINE spec. """


_FAILURES = (
    SourceMissing,
    ConfigError,
    WriterError,
    UnknownOutput,
    FenceLoadError,
    OutputLoadError,
    UsageError,
    LintError,
)


@app.command()
def tangle(
    source: Annotated[
        Path | None,
        typer.Argument(help="Markdown directory."),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Argument(help="Directory to write. Default: ./_build/<output>."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Run only this output."),
    ] = None,
) -> None:
    """ Concatenate file fences and write the output files. """
    _guard(lambda: _tangle(source, target, output))


@app.command()
def where(
    spec: Annotated[str, typer.Argument(help="Output FILE:LINE.")],
) -> None:
    """ Print the Markdown location that produced an output line. """
    _guard(lambda: _where(spec))


@app.command()
def check(
    source: Annotated[
        Path | None,
        typer.Argument(help="Markdown directory."),
    ] = None,
    json_output: Annotated[
        bool,
        typer.Option("--json", help="Print diagnostics as a JSON array."),
    ] = False,
) -> None:
    """ Report dead links and lint findings. """
    _guard(lambda: _check(source, json_output))


@app.command()
def watch(
    source: Annotated[
        Path | None,
        typer.Argument(help="Markdown directory."),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Argument(help="Directory to write. Default: ./_build/<output>."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", help="Run only this output."),
    ] = None,
) -> None:
    """ Re-tangle when Markdown under the source directory changes. """
    _guard(lambda: _watch(source, target, output))


@app.command()
def serve() -> None:
    """ Speak the language server protocol on standard input and output. """
    run_stdio()


def _guard(action: Callable[[], None]) -> None:
    try:
        action()
    except _FAILURES as err:
        typer.echo(f"error: {err}", err=True)
        raise typer.Exit(code=1) from None


def _tangle(
    source: Path | None,
    target: Path | None,
    output: str | None,
) -> None:
    root = Path.cwd()
    result = build_book(root, source, output)
    if _report(result.diagnostics):
        raise typer.Exit(code=1)
    _ = write_rendered(result, root, target)
    _ = _report(find_dead_links(result.book))


def _where(spec: str) -> None:
    root = Path.cwd()
    query = _parse_spec(spec, root)
    result = build_book(root, None, query.output_name)
    if _report(result.diagnostics):
        raise typer.Exit(code=1)
    site = _lookup(_maps(result), query)
    if site is None:
        place = f"{query.path.as_posix()}:{query.line}"
        raise UsageError(f"{place} is not in the tangle")
    typer.echo(f"{site.path.as_posix()}:{site.line}")


def _check(source: Path | None, json_output: bool) -> None:
    root = Path.cwd()
    result = build_book(root, source)
    diagnostics = _check_diagnostics(root, result)
    if json_output:
        typer.echo(_json(diagnostics))
    else:
        _ = _report(diagnostics)
    if any(item.severity == "error" for item in diagnostics):
        raise typer.Exit(code=1)


def _watch(
    source: Path | None,
    target: Path | None,
    output: str | None,
) -> None:
    root = Path.cwd()
    config = load_config(root)
    directory = source_directory(root, source, config)
    chosen = select_outputs(output, config.outputs)
    destinations = tuple(
        target_directory(item.name, target, root, len(chosen))
        for item in chosen
    )

    def cycle() -> None:
        built = build_book(root, directory, output)
        if _report(built.diagnostics):
            return
        _ = write_rendered(built, root, target)
        _ = _report(find_dead_links(built.book))

    cycle()
    watch_markdown(directory, cycle, ignore=_under(directory, destinations))


def _check_diagnostics(
    root: Path,
    result: BuildResult,
) -> tuple[Diagnostic, ...]:
    config = load_config(root)
    python = _python(result)
    lint = lint_python(root, python, config.check)
    return (
        *result.diagnostics,
        *find_dead_links(result.book),
        *lint,
    )


def _python(result: BuildResult) -> Rendered | None:
    for item in result.outputs:
        if item.name == "python":
            return item.rendered
    return None


def _under(directory: Path, destinations: Sequence[Path]) -> tuple[Path, ...]:
    source = directory.resolve()
    found: list[Path] = []
    for destination in destinations:
        resolved = destination.resolve()
        if resolved == source or _inside(resolved, source):
            found.append(resolved)
    return tuple(found)


def _inside(path: Path, root: Path) -> bool:
    try:
        _ = path.relative_to(root)
    except ValueError:
        return False
    return True


def _maps(result: BuildResult) -> tuple[SourceMap, ...]:
    return tuple(item.rendered.source_map for item in result.outputs)


def _report(diagnostics: Sequence[Diagnostic]) -> bool:
    failed = False
    for item in diagnostics:
        typer.echo(_format(item), err=True)
        if item.severity == "error":
            failed = True
    return failed


def _format(item: Diagnostic) -> str:
    return (
        f"{item.path.as_posix()}:{item.line}: "
        f"{item.severity} {item.code}: {item.message}"
    )


def _json(diagnostics: Sequence[Diagnostic]) -> str:
    payload = [
        {
            "path": item.path.as_posix(),
            "line": item.line,
            "severity": item.severity,
            "code": item.code,
            "message": item.message,
        }
        for item in diagnostics
    ]
    return json.dumps(payload)


@dataclass(frozen=True)
class _Query:
    """ An output line to look up. ``output_name`` is set for _build paths. """

    output_name: str | None
    path: Path
    line: int


def _parse_spec(spec: str, cwd: Path) -> _Query:
    raw_path, separator, raw_line = spec.rpartition(":")
    if not separator or not raw_path or not raw_line.isdigit():
        raise UsageError("expected FILE:LINE")
    output_name, path = _split_build_path(Path(raw_path), cwd)
    return _Query(output_name, path, int(raw_line))


def _split_build_path(spec_path: Path, cwd: Path) -> tuple[str | None, Path]:
    candidate = spec_path if spec_path.is_absolute() else cwd / spec_path
    build = (cwd / "_build").resolve()
    try:
        relative = candidate.resolve().relative_to(build)
    except ValueError:
        return None, Path(spec_path.as_posix())
    if len(relative.parts) < 2:
        return None, Path(spec_path.as_posix())
    return relative.parts[0], Path(*relative.parts[1:])


def _lookup(maps: Sequence[SourceMap], query: _Query) -> MarkdownSite | None:
    for source_map in maps:
        found = source_map.markdown_at(query.path, query.line)
        if found is not None:
            return found
    return None
