""" Run checkers on the python output and map findings to Markdown.

The shadow tree is ``<project>/.hydra/shadow``. A finding whose
output line is in the source map is reported on that Markdown line.
A finding with no mapping is reported on the first mapped line of
that output file, which is the first fence. A finding that still
cannot be mapped is a warning on the output path. No Python output
produces no diagnostics. Fragment rules listed on the Python fence
are dropped before findings are mapped. This module does not check
links.
"""

import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.check.errors import LintError
from hydra_tangler.check.pyright import Pyright
from hydra_tangler.check.reported import Reported
from hydra_tangler.check.ruff import Ruff
from hydra_tangler.check.shadow import prepare_shadow
from hydra_tangler.check.tool import Checker, CheckerCommands
from hydra_tangler.fences.exemptions import Exclusion, rules_for
from hydra_tangler.fences.python import Python
from hydra_tangler.model import Diagnostic
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.sourcemap import MarkdownSite, SourceMap, SourceRecord

Runner = Callable[[Sequence[str], Path], str]

_DEFAULT_SHADOW = Path(".hydra") / "shadow"


@dataclass(frozen=True)
class _Pass:
    """ One lint pass over a shadow tree. """

    project: Path
    commands: CheckerCommands
    shadow: Path
    python_files: tuple[Path, ...]
    exclusions: tuple[Exclusion, ...]
    rendered: Rendered
    run: Runner


def lint_python(
    project: Path,
    rendered: Rendered | None,
    commands: CheckerCommands,
    shadow: Path | None = None,
    checkers: Sequence[Checker] | None = None,
    run: Runner | None = None,
) -> tuple[Diagnostic, ...]:
    """ Lint the python output. Return nothing when there is no Python.

    ``checkers`` and ``run`` exist so tests can supply a fake tool
    without starting basedpyright or ruff.
    """
    if rendered is None:
        return ()
    directory = shadow if shadow is not None else project / _DEFAULT_SHADOW
    python_files = prepare_shadow(rendered.files, directory)
    if not python_files:
        return ()
    tools = checkers if checkers is not None else (Pyright(), Ruff())
    job = _Pass(
        project,
        commands,
        directory,
        python_files,
        Python.exclusions,
        rendered,
        run if run is not None else run_checker,
    )
    return _every(tools, job)


def _every(tools: Sequence[Checker], job: _Pass) -> tuple[Diagnostic, ...]:
    found: list[Diagnostic] = []
    for tool in tools:
        found.extend(_one_tool(tool, job))
    return tuple(found)


def run_checker(argv: Sequence[str], cwd: Path) -> str:
    """ Run ``argv`` in ``cwd`` and return stdout that contains JSON.

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


def _relative(shadow: Path, raw: str) -> Path | None:
    if not raw:
        return None
    candidate = Path(raw)
    if not candidate.is_absolute():
        return Path(candidate.as_posix())
    try:
        relative = candidate.resolve().relative_to(shadow.resolve())
    except ValueError:
        return None
    return Path(relative.as_posix())


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
