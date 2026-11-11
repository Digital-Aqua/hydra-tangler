""" Rebuild a book and collect the diagnostics a client should see.

The caller runs this on a worker thread. Link checks and lint share
that thread so the language-server loop stays free. This module does
not publish LSP messages or decide which rebuild is the newest.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.book import UnreadableSource
from hydra_tangler.check.errors import LintError
from hydra_tangler.check.links import find_dead_links
from hydra_tangler.check.lint import Runner, lint_python
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.failures import USER_FAILURES
from hydra_tangler.model import Book, Diagnostic
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.pipeline import BuildResult, build_book, write_rendered
from hydra_tangler.sourcemap import SourceMap
from hydra_tangler.writer import WriterError

# ``lint_python`` writes the tangled tree here. The language server
# points basedpyright at the same directory.
_SHADOW = Path(".hydra") / "shadow"


@dataclass(frozen=True)
class PythonSnapshot:
    """ Tangled Python files and the map back to Markdown. """

    shadow: Path
    source_map: SourceMap
    files: Mapping[Path, str]


@dataclass(frozen=True)
class Analysis:
    """ Diagnostics from one rebuild, plus why a step failed.

    ``source`` is the book root the diagnostics are relative to. It is
    ``None`` when the book could not be loaded. ``texts`` is the
    Markdown that was parsed, used to size diagnostic ranges.
    """

    diagnostics: tuple[Diagnostic, ...]
    texts: Mapping[Path, str]
    source: Path | None
    load_failure: str | None
    lint_failure: str | None
    write_failure: str | None
    python: PythonSnapshot | None


@dataclass(frozen=True)
class _Loaded:
    """ A book that loaded, and the text each document was parsed from. """

    result: BuildResult
    texts: Mapping[Path, str]


@dataclass(frozen=True)
class _Lint:
    """ Findings from the checkers, or the reason they did not run. """

    diagnostics: tuple[Diagnostic, ...]
    failure: str | None


def analyse(
    root: Path,
    overrides: Mapping[Path, str],
    write: bool,
    commands: CheckerCommands,
    run: Runner | None,
) -> Analysis:
    """ Load ``root``, optionally write outputs, then lint the Python. """
    loaded = _load(root, overrides)
    if isinstance(loaded, Analysis):
        return loaded
    return _with_checks(loaded, root, write, commands, run)


def _load(
    root: Path,
    overrides: Mapping[Path, str],
) -> Analysis | _Loaded:
    try:
        result = build_book(root, overrides=dict(overrides))
        texts = _texts(result.book, overrides)
    except USER_FAILURES as err:
        return _failed(str(err))
    return _Loaded(result, texts)


def _with_checks(
    loaded: _Loaded,
    root: Path,
    write: bool,
    commands: CheckerCommands,
    run: Runner | None,
) -> Analysis:
    result = loaded.result
    lint = _lint(root, result, commands, run)
    diagnostics = (
        *result.diagnostics,
        *find_dead_links(result.book),
        *lint.diagnostics,
    )
    return Analysis(
        diagnostics,
        loaded.texts,
        result.book.root,
        None,
        lint.failure,
        _maybe_write(result, root, write),
        _snapshot(root, result),
    )


def _failed(message: str) -> Analysis:
    return Analysis((), {}, None, message, None, None, None)


def _maybe_write(result: BuildResult, root: Path, write: bool) -> str | None:
    if not write or _has_error(result.diagnostics):
        return None
    try:
        _ = write_rendered(result, root, None)
    except WriterError as err:
        return str(err)
    return None


def _has_error(diagnostics: Sequence[Diagnostic]) -> bool:
    return any(item.severity == "error" for item in diagnostics)


def _lint(
    root: Path,
    result: BuildResult,
    commands: CheckerCommands,
    run: Runner | None,
) -> _Lint:
    try:
        found = lint_python(
            root,
            _python(result),
            commands,
            run=run,
        )
    except LintError as err:
        return _Lint((), str(err))
    return _Lint(found, None)


def _snapshot(root: Path, result: BuildResult) -> PythonSnapshot | None:
    rendered = _python(result)
    if rendered is None:
        return None
    files = decode_tangled_python(rendered)
    if not files:
        return None
    return PythonSnapshot(root / _SHADOW, rendered.source_map, files)


def decode_tangled_python(rendered: Rendered) -> dict[Path, str]:
    """ Decode tangled Python. An undecodable file names its path. """
    found: dict[Path, str] = {}
    for item in rendered.files.files:
        if item.path.suffix != ".py":
            continue
        try:
            found[item.path] = item.data.decode("utf-8")
        except UnicodeDecodeError as err:
            raise UnreadableSource(item.path, str(err)) from err
    return found


def _python(result: BuildResult) -> Rendered | None:
    for item in result.outputs:
        if item.name == "files":
            return item.rendered
    return None


def _texts(book: Book, overrides: Mapping[Path, str]) -> dict[Path, str]:
    return {
        document.path: _one_text(book.root, document.path, overrides)
        for document in book.documents
    }


def _one_text(
    root: Path,
    relative: Path,
    overrides: Mapping[Path, str],
) -> str:
    if relative in overrides:
        return overrides[relative]
    path = root / relative
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")
