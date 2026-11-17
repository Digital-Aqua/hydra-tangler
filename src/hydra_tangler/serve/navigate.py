"""Forward navigation queries to the shared basedpyright server.

The process is the one ``check`` also uses for diagnostics. Each
rebuild syncs the tangled Python into it. This module does not
rebuild the book and does not start a second basedpyright.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import final

from lsprotocol import types

from hydra_tangler.check.pyright_server import PyrightServer
from hydra_tangler.positions import FilePosition, output_position
from hydra_tangler.serve.analysis import PythonSnapshot
from hydra_tangler.serve.documents import markdown_relative
from hydra_tangler.serve.translate import (
    UnmappedLog,
    View,
    completion_from,
    hover_from,
    locations_from,
)


@final
class Navigation:
    """Hover, definition, and completion on the shared typechecker."""

    def __init__(
        self,
        on_error: Callable[[str], None],
        on_alert: Callable[[str], None],
    ) -> None:
        self._on_error = on_error
        self._on_alert = on_alert
        self._misses = UnmappedLog(on_error)
        self._lock = threading.Lock()
        self._source: Path | None = None
        self._python: PythonSnapshot | None = None
        self._server: PyrightServer | None = None
        self._exit_logged = False

    def bind(self, server: PyrightServer | None) -> None:
        """Use ``server`` for later queries. ``None`` disables them."""
        with self._lock:
            self._server = server

    def update(
        self,
        source: Path | None,
        python: PythonSnapshot | None,
    ) -> None:
        """Remember the latest tangle and push it when pyright is up."""
        with self._lock:
            self._source = source
            self._python = python
            server = self._server
        if server is None or python is None:
            return
        if not self._running(server):
            return
        server.sync(python.shadow, python.files)

    def hover(self, uri: str, line: int, character: int) -> types.Hover | None:
        """Hover at a Markdown position, or None outside a Python fence."""
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/hover",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._after(placed.server)
        if payload is None or placed.server.request_failed():
            return None
        return hover_from(
            placed.view,
            placed.output.path,
            payload,
            self._misses,
        )

    def definition(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[types.Location] | None:
        """Definition at a Markdown position."""
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/definition",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._after(placed.server)
        if payload is None or placed.server.request_failed():
            return None
        return locations_from(placed.view, payload, self._misses)

    def completion(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> types.CompletionList | None:
        """Completions at a Markdown position."""
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/completion",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._after(placed.server)
        if payload is None or placed.server.request_failed():
            return None
        return completion_from(
            placed.view,
            placed.output.path,
            payload,
            self._misses,
        )

    def stop(self) -> None:
        """Stop the shared server if this session owns the binding."""
        with self._lock:
            server = self._server
            self._server = None
        if server is not None:
            server.stop()

    def _placed(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> _Placed | None:
        with self._lock:
            ready = self._ready(uri, line, character)
            server = self._server
        if ready is None or server is None:
            return None
        if not self._running(server):
            return None
        return _Placed(server, ready.view, ready.output, ready.file_uri)

    def _running(self, server: PyrightServer) -> bool:
        if server.ensure_started():
            with self._lock:
                self._exit_logged = False
            return True
        self._announce(server)
        self._note_dead(server)
        return False

    def _ready(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> _Ready | None:
        """Resolve a fence position. The caller holds the lock."""
        python = self._python
        source = self._source
        if python is None or source is None:
            return None
        relative = markdown_relative(source, uri)
        if relative is None:
            return None
        output = output_position(python.source_map, relative, line, character)
        if output is None:
            return None
        return _Ready(
            _view(python, source, uri, relative),
            output,
            _file_uri(python.shadow, output.path),
        )

    def _after(self, server: PyrightServer) -> None:
        if server.request_failed() or server.exited():
            self._announce(server)
            self._note_dead(server)

    def _announce(self, server: PyrightServer) -> None:
        detail = server.claim_failure()
        if detail is not None:
            self._on_alert(detail)

    def _note_dead(self, server: PyrightServer) -> None:
        if not server.exited():
            return
        with self._lock:
            if self._server is not server or self._exit_logged:
                return
            self._exit_logged = True
        self._on_error(server.failure_detail())


@dataclass(frozen=True)
class _Ready:
    view: View
    output: FilePosition
    file_uri: str


@dataclass(frozen=True)
class _Placed:
    server: PyrightServer
    view: View
    output: FilePosition
    file_uri: str


def _view(
    python: PythonSnapshot,
    source: Path,
    uri: str,
    relative: Path,
) -> View:
    return View(
        source_map=python.source_map,
        shadow=python.shadow,
        source=source,
        request_uri=uri,
        request_path=relative,
    )


def _at(uri: str, line: int, character: int) -> dict[str, object]:
    return {
        "textDocument": {"uri": uri},
        "position": {"line": line, "character": character},
    }


def _file_uri(shadow: Path, path: Path) -> str:
    return (shadow / path).resolve().as_uri()
