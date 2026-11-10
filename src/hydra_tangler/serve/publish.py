""" Publish Markdown diagnostics and clear ones that went stale.

A file that had diagnostics and now has none receives an empty list,
which is how a client removes squiggles. This module does not rebuild
the book and does not run checkers.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import final
from urllib.parse import unquote

from lsprotocol import types
from pygls.lsp.server import LanguageServer

from hydra_tangler.model import Diagnostic
from hydra_tangler.serve.analysis import Analysis
from hydra_tangler.serve.status import StatusReport, status_for


@final
class DiagnosticPublisher:
    """ Remember which URIs were published so a later build can clear them. """

    def __init__(self, server: LanguageServer) -> None:
        self._server = server
        self._sent: set[str] = set()

    def publish(
        self,
        analysis: Analysis,
        opens: Mapping[Path, str],
    ) -> StatusReport:
        """ Send the diagnostics in ``analysis`` and clear the rest. """
        source = analysis.source
        if source is None:
            return status_for(analysis.diagnostics)
        current = self._send_current(analysis, source, opens)
        self._clear_stale(current)
        self._sent = current
        return status_for(analysis.diagnostics)

    def _send_current(
        self,
        analysis: Analysis,
        source: Path,
        opens: Mapping[Path, str],
    ) -> set[str]:
        grouped = _by_path(analysis.diagnostics)
        current: set[str] = set()
        for path, items in grouped.items():
            uri = _choose_uri(source, path, opens)
            text = analysis.texts.get(path, "")
            self._emit(uri, items, text)
            current.add(uri)
        return current

    def _clear_stale(self, current: set[str]) -> None:
        for uri in self._sent - current:
            self._emit(uri, (), "")

    def _emit(
        self,
        uri: str,
        diagnostics: Sequence[Diagnostic],
        text: str,
    ) -> None:
        params = types.PublishDiagnosticsParams(
            uri=uri,
            diagnostics=[_diagnostic(item, text) for item in diagnostics],
            version=_version(self._server, uri),
        )
        self._server.text_document_publish_diagnostics(params)


def _by_path(
    diagnostics: Sequence[Diagnostic],
) -> dict[Path, tuple[Diagnostic, ...]]:
    grouped: dict[Path, list[Diagnostic]] = {}
    for item in diagnostics:
        grouped.setdefault(item.path, []).append(item)
    return {path: tuple(items) for path, items in grouped.items()}


def _choose_uri(
    source: Path,
    relative: Path,
    opens: Mapping[Path, str],
) -> str:
    known = opens.get(relative)
    if known is not None:
        return known
    return (source / relative).resolve().as_uri()


def _diagnostic(item: Diagnostic, text: str) -> types.Diagnostic:
    return types.Diagnostic(
        range=_line_range(text, item.line),
        message=item.message,
        severity=_severity(item.severity),
        code=item.code,
        source="hydra",
    )


def _line_range(text: str, line: int) -> types.Range:
    number = max(line, 1) - 1
    rows = text.splitlines()
    width = 0
    if number < len(rows):
        width = _utf16_units(rows[number])
    return types.Range(
        start=types.Position(line=number, character=0),
        end=types.Position(line=number, character=width),
    )


def _utf16_units(text: str) -> int:
    """ LSP columns count UTF-16 code units, not Unicode code points. """
    return len(text.encode("utf-16-le")) // 2


def _severity(value: str) -> types.DiagnosticSeverity:
    if value == "warning":
        return types.DiagnosticSeverity.Warning
    return types.DiagnosticSeverity.Error


def _version(server: LanguageServer, uri: str) -> int | None:
    documents = server.workspace.text_documents
    document = documents.get(unquote(uri))
    if document is None:
        document = documents.get(uri)
    if document is None or not isinstance(document.version, int):
        return None
    return document.version
