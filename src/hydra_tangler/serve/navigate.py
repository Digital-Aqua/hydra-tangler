""" Forward navigation queries to a basedpyright subprocess.

The process starts on the first hover, definition, or completion.
While it is running, each rebuild sends ``didOpen`` for a new Python
file, a full ``didChange`` when its text differs, and ``didClose``
when it disappears. This module does not rebuild the book.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import final

from lsprotocol import types

from hydra_tangler.serve.analysis import PythonSnapshot
from hydra_tangler.serve.documents import markdown_relative
from hydra_tangler.serve.positions import FilePosition, output_position
from hydra_tangler.serve.pyright import PyrightServer, default_command
from hydra_tangler.serve.translate import (
    View,
    completion_from,
    hover_from,
    locations_from,
)


@final
class Navigation:
    """ One basedpyright process for the current shadow tree. """

    def __init__(self, on_error: Callable[[str], None]) -> None:
        self._on_error = on_error
        self._lock = threading.Lock()
        self._project: Path | None = None
        self._command: tuple[str, ...] = ()
        self._source: Path | None = None
        self._python: PythonSnapshot | None = None
        self._server: PyrightServer | None = None
        self._opened: set[Path] = set()
        self._text: dict[Path, str] = {}
        self._version: dict[Path, int] = {}
        self._failed = False

    def bind(self, project: Path, command: tuple[str, ...]) -> None:
        """ Remember the project used to launch basedpyright. """
        with self._lock:
            self._project = project
            self._command = command

    def update(
        self,
        source: Path | None,
        python: PythonSnapshot | None,
    ) -> None:
        """ Remember the latest tangle and push it if pyright is up. """
        with self._lock:
            previous = self._python
            self._source = source
            self._python = python
            server = self._server
            if server is None:
                self._forget_closed(python)
                return
            if python is None:
                self._close_all(server, previous)
                return
            self._push(server, python)

    def hover(self, uri: str, line: int, character: int) -> types.Hover | None:
        """ Hover at a Markdown position, or None outside a Python fence. """
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/hover",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._note_dead(placed.server)
        if payload is None:
            return None
        return hover_from(placed.view, placed.output.path, payload)

    def definition(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> list[types.Location] | None:
        """ Definition at a Markdown position. """
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/definition",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._note_dead(placed.server)
        if payload is None:
            return None
        return locations_from(placed.view, payload)

    def completion(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> types.CompletionList | None:
        """ Completions at a Markdown position. """
        placed = self._placed(uri, line, character)
        if placed is None:
            return None
        payload = placed.server.request(
            "textDocument/completion",
            _at(placed.file_uri, placed.output.line, placed.output.character),
        )
        self._note_dead(placed.server)
        if payload is None:
            return None
        return completion_from(placed.view, placed.output.path, payload)

    def stop(self) -> None:
        """ Kill the subprocess if it was started. """
        with self._lock:
            server = self._server
            self._server = None
            self._opened.clear()
            self._text.clear()
            self._version.clear()
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
        if ready is None:
            return None
        server = ready.server if ready.server is not None else self._start()
        if server is None:
            return None
        return _Placed(server, ready.view, ready.output, ready.file_uri)

    def _ready(
        self,
        uri: str,
        line: int,
        character: int,
    ) -> _Ready | None:
        """ Resolve a fence position. The caller holds the lock. """
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
            self._server,
            _view(python, source, uri, relative),
            output,
            _file_uri(python.shadow, output.path),
        )

    def _start(self) -> PyrightServer | None:
        with self._lock:
            if self._server is not None:
                return self._server
            if self._failed or self._project is None or self._python is None:
                return None
            command = self._command or default_command(self._project)
            shadow = self._python.shadow
        server = PyrightServer(command, shadow)
        if not server.start():
            self._give_up()
            return None
        return self._adopt(server)

    def _give_up(self) -> None:
        with self._lock:
            if self._server is None:
                self._failed = True
        self._on_error("basedpyright language server did not start")

    def _adopt(self, server: PyrightServer) -> PyrightServer:
        with self._lock:
            current = self._server
            if current is not None:
                duplicate = server
                chosen = current
            else:
                duplicate = None
                chosen = server
                self._server = server
                if self._python is not None:
                    self._push(server, self._python)
        if duplicate is not None:
            duplicate.stop()
        return chosen

    def _note_dead(self, server: PyrightServer) -> None:
        if not server.exited():
            return
        with self._lock:
            if self._server is not server:
                return
            self._server = None
            self._opened.clear()
            self._text.clear()
            self._version.clear()

    def _close_all(
        self,
        server: PyrightServer,
        previous: PythonSnapshot | None,
    ) -> None:
        if previous is None:
            return
        for path in list(self._opened):
            server.notify(
                "textDocument/didClose",
                _identifier(previous.shadow, path),
            )
            self._drop(path)

    def _forget_closed(self, python: PythonSnapshot | None) -> None:
        if python is None:
            self._opened.clear()
            self._text.clear()
            self._version.clear()
            return
        missing = [path for path in self._opened if path not in python.files]
        for path in missing:
            self._drop(path)

    def _push(self, server: PyrightServer, python: PythonSnapshot) -> None:
        self._close_missing(server, python)
        for path, text in python.files.items():
            self._sync_file(server, python.shadow, path, text)

    def _close_missing(
        self,
        server: PyrightServer,
        python: PythonSnapshot,
    ) -> None:
        missing = [path for path in self._opened if path not in python.files]
        for path in missing:
            server.notify(
                "textDocument/didClose",
                _identifier(python.shadow, path),
            )
            self._drop(path)

    def _sync_file(
        self,
        server: PyrightServer,
        shadow: Path,
        path: Path,
        text: str,
    ) -> None:
        if path not in self._opened:
            self._version[path] = 1
            server.notify(
                "textDocument/didOpen",
                _opened(shadow, path, text, 1),
            )
            self._opened.add(path)
            self._text[path] = text
            return
        if self._text.get(path) == text:
            return
        version = self._version.get(path, 1) + 1
        self._version[path] = version
        self._text[path] = text
        server.notify(
            "textDocument/didChange",
            _changed(shadow, path, text, version),
        )

    def _drop(self, path: Path) -> None:
        self._opened.discard(path)
        _ = self._text.pop(path, None)
        _ = self._version.pop(path, None)


@dataclass(frozen=True)
class _Ready:
    server: PyrightServer | None
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


def _identifier(shadow: Path, path: Path) -> dict[str, object]:
    return {"textDocument": {"uri": _file_uri(shadow, path)}}


def _opened(
    shadow: Path,
    path: Path,
    text: str,
    version: int,
) -> dict[str, object]:
    return {
        "textDocument": {
            "uri": _file_uri(shadow, path),
            "languageId": "python",
            "version": version,
            "text": text,
        }
    }


def _changed(
    shadow: Path,
    path: Path,
    text: str,
    version: int,
) -> dict[str, object]:
    return {
        "textDocument": {"uri": _file_uri(shadow, path), "version": version},
        "contentChanges": [{"text": text}],
    }


def _file_uri(shadow: Path, path: Path) -> str:
    return (shadow / path).resolve().as_uri()
