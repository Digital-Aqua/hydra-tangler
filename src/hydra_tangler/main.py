""" Command line: tangle, where, check, watch, and serve.

Document problems are printed as diagnostics. Error severity exits
1, without a traceback. Warning severity, including dead links, does
not. ``serve`` speaks the language server protocol on stdio and does
not print diagnostics.
"""

import json
import shlex
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer

from hydra_tangler.check.links import find_dead_links
from hydra_tangler.check.lint import lint_python
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.failures import USER_FAILURES
from hydra_tangler.model import Diagnostic
from hydra_tangler.mounting import merged_source_map
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.pipeline import (
    BuildResult,
    build_book,
    source_directory,
    target_directory,
    write_rendered,
)
from hydra_tangler.serve.server import run_stdio
from hydra_tangler.watch import watch_markdown

app = typer.Typer(add_completion=False, help="Tangle Markdown into code.")


class UsageError(Exception):
    """ The command line value is not a FILE:LINE spec. """


# ``UsageError`` is raised only while parsing a command-line spec.
_FAILURES = (*USER_FAILURES, UsageError)


@app.command()
def tangle(
    source: Annotated[
        Path | None,
        typer.Argument(help="Markdown directory."),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Argument(help="Directory to write. Default: ./_build."),
    ] = None,
    output: Annotated[
        list[str] | None,
        typer.Option(
            "--output",
            help="Output to run. Repeat to select more than one.",
        ),
    ] = None,
    no_sourcemap: Annotated[
        bool,
        typer.Option("--no-sourcemap", help="Do not write sourcemap.json."),
    ] = False,
) -> None:
    """ Concatenate file fences and write the output files. """
    _guard(lambda: _tangle(source, target, output, no_sourcemap))


@app.command()
def where(
    spec: Annotated[
        str,
        typer.Argument(
            help="Target-relative FILE:LINE, such as mypackage/m.py:12.",
        ),
    ],
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
    pyright_command: Annotated[
        str | None,
        typer.Option(
            "--pyright-command",
            help="Shell-style argv for basedpyright. Default: uv run.",
        ),
    ] = None,
    ruff_command: Annotated[
        str | None,
        typer.Option(
            "--ruff-command",
            help="Shell-style argv for ruff. Default: uv run.",
        ),
    ] = None,
) -> None:
    """ Report dead links and lint findings. """
    _guard(lambda: _check(source, json_output, pyright_command, ruff_command))


@app.command()
def watch(
    source: Annotated[
        Path | None,
        typer.Argument(help="Markdown directory."),
    ] = None,
    target: Annotated[
        Path | None,
        typer.Argument(help="Directory to write. Default: ./_build."),
    ] = None,
    output: Annotated[
        list[str] | None,
        typer.Option(
            "--output",
            help="Output to run. Repeat to select more than one.",
        ),
    ] = None,
    no_sourcemap: Annotated[
        bool,
        typer.Option("--no-sourcemap", help="Do not write sourcemap.json."),
    ] = False,
) -> None:
    """ Re-tangle when Markdown under the source directory changes. """
    _guard(lambda: _watch(source, target, output, no_sourcemap))


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
    output: list[str] | None,
    no_sourcemap: bool,
) -> None:
    root = Path.cwd()
    result = build_book(root, source, _names(output), target=target)
    if _report(result.diagnostics):
        raise typer.Exit(code=1)
    _ = write_rendered(result, root, target, sourcemap=not no_sourcemap)
    _ = _report(find_dead_links(result.book))


def _where(spec: str) -> None:
    root = Path.cwd()
    query = _parse_spec(spec, root)
    result = build_book(root, None)
    if _report(result.diagnostics):
        raise typer.Exit(code=1)
    source_map = merged_source_map(result.outputs)
    site = source_map.markdown_at(query.path, query.line)
    if site is None:
        place = f"{query.path.as_posix()}:{query.line}"
        raise UsageError(f"{place} is not in the tangle")
    typer.echo(f"{site.path.as_posix()}:{site.line}")


def _check(
    source: Path | None,
    json_output: bool,
    pyright_command: str | None,
    ruff_command: str | None,
) -> None:
    root = Path.cwd()
    result = build_book(root, source)
    commands = CheckerCommands(
        _command(pyright_command),
        _command(ruff_command),
    )
    diagnostics = _check_diagnostics(root, result, commands)
    if json_output:
        typer.echo(_json(diagnostics))
    else:
        _ = _report(diagnostics)
    if any(item.severity == "error" for item in diagnostics):
        raise typer.Exit(code=1)


def _watch(
    source: Path | None,
    target: Path | None,
    output: list[str] | None,
    no_sourcemap: bool,
) -> None:
    root = Path.cwd()
    names = _names(output)
    directory = source_directory(root, source)
    destination = target_directory(target, root)

    def cycle() -> None:
        built = build_book(root, directory, names, target=target)
        if _report(built.diagnostics):
            return
        _ = write_rendered(
            built,
            root,
            target,
            sourcemap=not no_sourcemap,
        )
        _ = _report(find_dead_links(built.book))

    cycle()
    watch_markdown(directory, cycle, ignore=_under(directory, (destination,)))


def _names(output: list[str] | None) -> tuple[str, ...]:
    if not output:
        return ()
    return tuple(output)


def _command(text: str | None) -> tuple[str, ...]:
    """ Split a shell-style argv. ``None`` keeps the checker default. """
    if text is None:
        return ()
    try:
        words = shlex.split(text)
    except ValueError as err:
        raise UsageError(f"bad command: {err}") from err
    return tuple(words)


def _check_diagnostics(
    root: Path,
    result: BuildResult,
    commands: CheckerCommands,
) -> tuple[Diagnostic, ...]:
    python = _python(result)
    lint = lint_python(root, python, commands)
    return (
        *result.diagnostics,
        *find_dead_links(result.book),
        *lint,
    )


def _python(result: BuildResult) -> Rendered | None:
    for item in result.outputs:
        if item.name == "files":
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
    """ A target-relative output line to look up. """

    path: Path
    line: int


def _parse_spec(spec: str, cwd: Path) -> _Query:
    raw_path, separator, raw_line = spec.rpartition(":")
    if not separator or not raw_path or not raw_line.isdigit():
        raise UsageError("expected FILE:LINE")
    return _Query(_target_relative(Path(raw_path), cwd), int(raw_line))


def _target_relative(spec_path: Path, cwd: Path) -> Path:
    """ Strip a ``_build/`` prefix so a built path matches the map. """
    candidate = spec_path if spec_path.is_absolute() else cwd / spec_path
    build = (cwd / "_build").resolve()
    try:
        relative = candidate.resolve().relative_to(build)
    except ValueError:
        return Path(spec_path.as_posix())
    return Path(relative.as_posix())
