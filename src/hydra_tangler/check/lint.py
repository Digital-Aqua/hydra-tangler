"""Run checkers on the python output and map findings to Markdown.

The shadow tree is ``<project>/.hydra/shadow``. basedpyright is one
language server: its diagnostics are mapped with columns through the
source map. Ruff stays a one-shot JSON checker. A finding whose
output line is in the source map is reported on that Markdown line.
A finding with no mapping is reported on the first mapped line of
that output file, which is the first fence. A finding that still
cannot be mapped is a warning on the output path. No Python output
produces no diagnostics. Fragment rules listed on the Python fence
are dropped before ruff findings are mapped. Book-level checker
defaults are applied by the checkers themselves. This module does
not check links.
"""

import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import final
from urllib.parse import unquote, urlparse

from hydra_tangler.check.errors import LintError
from hydra_tangler.check.pyright_server import (
    BasedpyrightCheck,
    TypeChecker,
    TypeReport,
)
from hydra_tangler.check.reported import Reported
from hydra_tangler.check.ruff import Ruff
from hydra_tangler.check.shadow import prepare_shadow
from hydra_tangler.check.tool import Checker, CheckerCommands
from hydra_tangler.fences.exemptions import Exclusion, rules_for
from hydra_tangler.fences.python import Python
from hydra_tangler.model import Diagnostic, Severity
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.positions import FileRange, markdown_range
from hydra_tangler.sourcemap import MarkdownSite, SourceMap, SourceRecord

Runner = Callable[[Sequence[str], Path], str]

_DEFAULT_SHADOW = Path(".hydra") / "shadow"


@dataclass(frozen=True)
class _Pass:
    """One lint pass over a shadow tree."""

    project: Path
    commands: CheckerCommands
    shadow: Path
    python_files: tuple[Path, ...]
    texts: Mapping[Path, str]
    exclusions: tuple[Exclusion, ...]
    rendered: Rendered
    run: Runner
    typecheck: TypeChecker | None


def lint_python(
    project: Path,
    rendered: Rendered | None,
    commands: CheckerCommands,
    shadow: Path | None = None,
    checkers: Sequence[Checker] | None = None,
    run: Runner | None = None,
    typecheck: TypeChecker | None = None,
) -> tuple[Diagnostic, ...]:
    """Lint the python output. Return nothing when there is no Python.

    ``checkers`` and ``run`` exist so tests can supply a fake ruff
    without starting it. ``typecheck`` replaces the basedpyright
    language server. When ``checkers`` is set and ``typecheck`` is
    omitted, typechecking is skipped.
    """
    if rendered is None:
        return ()
    directory = shadow if shadow is not None else project / _DEFAULT_SHADOW
    python_files = prepare_shadow(rendered.files, directory)
    texts = _texts(rendered)
    if not python_files:
        return ()
    job = _Pass(
        project,
        commands,
        directory,
        python_files,
        texts,
        Python.exclusions,
        rendered,
        run if run is not None else run_checker,
        typecheck,
    )
    return (
        *_types(job, checkers is None),
        *_ruff(job, checkers),
    )


def _types(job: _Pass, default: bool) -> tuple[Diagnostic, ...]:
    checker = _typechecker(job, default)
    if checker is None:
        return ()
    reports = checker.check(job.project, job.shadow, job.texts)
    return map_type_reports(reports, job.shadow, job.rendered.source_map)


def _typechecker(job: _Pass, default: bool) -> TypeChecker | None:
    if job.typecheck is not None:
        return job.typecheck
    if not default:
        return None
    checker = BasedpyrightCheck(job.commands.pyright, job.project)
    return _Closing(checker)


@final
class _Closing:
    """Run one owned language server and stop it afterwards."""

    def __init__(self, checker: BasedpyrightCheck) -> None:
        self._checker: BasedpyrightCheck = checker

    def check(
        self,
        book: Path,
        shadow: Path,
        files: Mapping[Path, str],
    ) -> tuple[TypeReport, ...]:
        try:
            return self._checker.check(book, shadow, files)
        finally:
            self._checker.close()


def _ruff(
    job: _Pass,
    checkers: Sequence[Checker] | None,
) -> tuple[Diagnostic, ...]:
    tools = checkers if checkers is not None else (Ruff(),)
    found: list[Diagnostic] = []
    for tool in tools:
        found.extend(_one_tool(tool, job))
    return tuple(found)


def map_type_reports(
    reports: Sequence[TypeReport],
    shadow: Path,
    source_map: SourceMap,
) -> tuple[Diagnostic, ...]:
    """Map basedpyright ranges onto Markdown, keeping columns."""
    found: list[Diagnostic] = []
    for report in reports:
        item = _mapped_report(report, shadow, source_map)
        if item is not None:
            found.append(item)
    return tuple(found)


def run_checker(argv: Sequence[str], cwd: Path) -> str:
    """Run ``argv`` in ``cwd`` and return stdout that contains JSON.

    A missing program, or output that is not JSON, raises ``LintError``.
    A non-zero exit is fine when the checker still printed JSON.
    """
    if not argv:
        raise LintError("checker command is empty")
    completed = _spawn(argv, cwd)
    return _stdout(argv[0], completed)


def _one_tool(tool: Checker, job: _Pass) -> tuple[Diagnostic, ...]:
    command = (
        *tool.argv(job.project, tool.configured(job.commands)),
        *tool.suppress(rules_for(job.exclusions, tool.name)),
        *(str(path) for path in job.python_files),
    )
    stdout = job.run(command, job.shadow)
    return tuple(
        _mapped(item, job.shadow, job.rendered.source_map)
        for item in tool.read(stdout)
    )


def _texts(rendered: Rendered) -> dict[Path, str]:
    found: dict[Path, str] = {}
    for item in rendered.files.files:
        if item.path.suffix != ".py":
            continue
        try:
            found[item.path] = item.data.decode("utf-8")
        except UnicodeDecodeError as err:
            raise LintError(f"cannot read {item.path.as_posix()}") from err
    return found


def _mapped_report(
    report: TypeReport,
    shadow: Path,
    source_map: SourceMap,
) -> Diagnostic | None:
    relative = _relative(shadow, report.file)
    if relative is None:
        return _unmapped_report(report)
    span = markdown_range(source_map, _file_range(relative, report))
    if span is None:
        return _fallback(report, source_map, relative)
    return Diagnostic(
        span.path,
        span.start_line + 1,
        _level(report.severity),
        _code(report.rule),
        report.message,
        span.start_character,
        span.end_line + 1,
        span.end_character,
    )


def _file_range(relative: Path, report: TypeReport) -> FileRange:
    return FileRange(
        relative,
        report.start_line,
        report.start_character,
        report.end_line,
        report.end_character,
    )


def _fallback(
    report: TypeReport,
    source_map: SourceMap,
    relative: Path,
) -> Diagnostic | None:
    site = _first_site(source_map, relative)
    if site is None:
        return _unmapped_report(report)
    return Diagnostic(
        site.path,
        site.line,
        _level(report.severity),
        _code(report.rule),
        report.message,
    )


def _mapped(
    item: Reported,
    shadow: Path,
    source_map: SourceMap,
) -> Diagnostic:
    relative = _relative(shadow, item.file)
    site = _site(source_map, relative, item.line)
    if relative is None or site is None:
        return _unmapped(item)
    return Diagnostic(
        site.path,
        site.line,
        item.severity,
        item.code,
        item.message,
    )


def _site(
    source_map: SourceMap,
    relative: Path | None,
    line: int,
) -> MarkdownSite | None:
    if relative is None:
        return None
    site = source_map.markdown_at(relative, line)
    if site is None:
        return _first_site(source_map, relative)
    return site


def _unmapped(item: Reported) -> Diagnostic:
    return Diagnostic(
        Path(item.file),
        item.line,
        "warning",
        "unmapped-finding",
        item.message,
    )


def _unmapped_report(report: TypeReport) -> Diagnostic:
    return Diagnostic(
        Path(report.file),
        report.start_line + 1,
        "warning",
        "unmapped-finding",
        report.message,
    )


def _first_site(source_map: SourceMap, relative: Path) -> MarkdownSite | None:
    found: SourceRecord | None = None
    for record in source_map.records:
        if record.output.path != relative:
            continue
        if found is None or record.output.line < found.output.line:
            found = record
    if found is None:
        return None
    return found.markdown


def _code(rule: str) -> str:
    if not rule:
        return "basedpyright"
    return f"basedpyright:{rule}"


def _level(severity: str) -> Severity:
    if severity == "error":
        return "error"
    return "warning"


def _relative(shadow: Path, raw: str) -> Path | None:
    if not raw:
        return None
    if raw.startswith("file:"):
        return _from_uri(shadow, raw)
    candidate = Path(raw)
    if not candidate.is_absolute():
        return Path(candidate.as_posix())
    try:
        relative = candidate.resolve().relative_to(shadow.resolve())
    except ValueError:
        return None
    return Path(relative.as_posix())


def _from_uri(shadow: Path, raw: str) -> Path | None:
    path = _uri_path(raw)
    if path is None:
        return None
    try:
        relative = path.resolve().relative_to(shadow.resolve())
    except ValueError:
        return None
    return Path(relative.as_posix())


def _uri_path(uri: str) -> Path | None:
    parsed = urlparse(uri)
    if parsed.scheme != "file" or not parsed.path:
        return None
    return Path(unquote(parsed.path))


def _spawn(
    argv: Sequence[str],
    cwd: Path,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            list(argv),
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as err:
        raise LintError(f"cannot run {argv[0]}") from err
    except OSError as err:
        detail = err.strerror or "failed to start"
        raise LintError(f"cannot run {argv[0]}: {detail}") from err


def _stdout(name: str, completed: subprocess.CompletedProcess[str]) -> str:
    text = completed.stdout.strip()
    if "{" in text or "[" in text:
        return text
    detail = completed.stderr.strip() or text
    if not detail:
        detail = f"exited {completed.returncode}"
    raise LintError(f"{name}: {detail.splitlines()[-1]}")
