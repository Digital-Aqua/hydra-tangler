""" A tiny JSON-RPC client for language-server tests.

Speaks Content-Length framing on a pair of binary streams. It does
not know which methods Hydra implements.
"""

import json
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, cast, final

from hydra_tangler.serve.status import HYDRA_STATUS


@dataclass(frozen=True)
class RpcNote:
    """ One notification the server sent. """

    method: str
    params: object


@final
class LspClient:
    """ Read server messages on a background thread. """

    def __init__(self, reader: BinaryIO, writer: BinaryIO) -> None:
        self._reader = reader
        self._writer = writer
        self._write_lock = threading.Lock()
        self._condition = threading.Condition()
        self._notes: list[RpcNote] = []
        self._results: dict[int, object] = {}
        self._errors: dict[int, str] = {}
        self._next = 1
        self._status_at = 0
        self._closed = False
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def request(
        self,
        method: str,
        params: object,
        timeout: float = 5,
    ) -> object:
        """ Send a request and return its result. """
        number = self._next
        self._next += 1
        self._send(
            {
                "jsonrpc": "2.0",
                "id": number,
                "method": method,
                "params": params,
            }
        )
        return self._wait_result(number, timeout)

    def notify(self, method: str, params: object) -> None:
        """ Send a notification. """
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def initialize(
        self,
        root: Path,
        *,
        write: bool,
        pyright: tuple[str, ...] = (),
        pyright_server: tuple[str, ...] = (),
        timeout: float = 8,
    ) -> object:
        """ Initialize against ``root`` and announce ``initialized``. """
        folder = root.resolve()
        uri = folder.as_uri()
        options: dict[str, object] = {"write": write}
        if pyright:
            options["pyrightCommand"] = list(pyright)
        if pyright_server:
            options["pyrightServerCommand"] = list(pyright_server)
        result = self.request(
            "initialize",
            {
                "processId": _pid(),
                "rootPath": str(folder),
                "rootUri": uri,
                "capabilities": {},
                "initializationOptions": options,
                "workspaceFolders": [{"uri": uri, "name": "book"}],
            },
            timeout=timeout,
        )
        self.notify("initialized", {})
        return result

    def open_markdown(self, uri: str, text: str, version: int = 1) -> None:
        """ Send ``textDocument/didOpen`` for a Markdown buffer. """
        self.notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": "markdown",
                    "version": version,
                    "text": text,
                }
            },
        )

    def change_markdown(self, uri: str, text: str, version: int) -> None:
        """ Send a full-document ``textDocument/didChange``. """
        self.notify(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": text}],
            },
        )

    def save_markdown(self, uri: str, text: str) -> None:
        """ Send ``textDocument/didSave`` including the buffer text. """
        self.notify(
            "textDocument/didSave",
            {"textDocument": {"uri": uri}, "text": text},
        )

    def wait_status(self, state: str, timeout: float = 4) -> dict[str, object]:
        """ Return the next ``hydra/status`` whose state matches. """
        start = self._status_at

        def ready() -> dict[str, object] | None:
            return self._take_status(start, state)

        return self._wait(ready, timeout)

    def wait_diagnostics(
        self,
        uri: str,
        predicate: Callable[[list[object]], bool],
        timeout: float = 4,
    ) -> list[object]:
        """ Return the latest diagnostics for ``uri`` once they match. """

        def ready() -> list[object] | None:
            items = self._latest_diagnostics(uri)
            if items is None or not predicate(items):
                return None
            return items

        return self._wait(ready, timeout)

    def wait_message(
        self,
        method: str,
        needle: str,
        timeout: float = 4,
    ) -> str:
        """ Return a notification message once it contains ``needle``. """

        def ready() -> str | None:
            return _message_with(self._notes, method, needle)

        return self._wait(ready, timeout)

    def messages(self, method: str) -> list[str]:
        """ Every notification message seen for ``method``. """
        with self._condition:
            return _messages(self._notes, method)

    def close(self) -> None:
        """ Close the write stream so the server sees end of input. """
        with self._write_lock:
            self._writer.close()

    def debug(self) -> str:
        """ A short list of notifications seen so far. """
        with self._condition:
            return self._debug()

    def _take_status(self, start: int, state: str) -> dict[str, object] | None:
        index = start
        while index < len(self._notes):
            note = self._notes[index]
            index += 1
            if note.method != HYDRA_STATUS:
                continue
            payload = as_dict(note.params)
            if payload is None or payload.get("state") != state:
                continue
            self._status_at = index
            return payload
        return None

    def _latest_diagnostics(self, uri: str) -> list[object] | None:
        found: list[object] | None = None
        for note in self._notes:
            items = _diagnostics_for(note, uri)
            if items is not None:
                found = items
        return found

    def _wait[T](self, ready: Callable[[], T | None], timeout: float) -> T:
        deadline = time.monotonic() + timeout
        with self._condition:
            while True:
                found = ready()
                if found is not None:
                    return found
                self._pause(deadline)

    def _wait_result(self, number: int, timeout: float) -> object:
        deadline = time.monotonic() + timeout
        with self._condition:
            while number not in self._results and number not in self._errors:
                self._pause(deadline)
            if number in self._errors:
                raise RuntimeError(self._errors[number])
            return self._results[number]

    def _pause(self, deadline: float) -> None:
        if self._closed:
            raise TimeoutError(self._debug())
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(self._debug())
        _ = self._condition.wait(remaining)

    def _send(self, payload: dict[str, object]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii")
        with self._write_lock:
            _ = self._writer.write(header)
            _ = self._writer.write(raw)
            self._writer.flush()

    def _read_loop(self) -> None:
        while True:
            message = _read_message(self._reader)
            if message is None:
                self._mark_closed()
                return
            self._store(message)

    def _store(self, message: dict[str, object]) -> None:
        with self._condition:
            self._keep(message)
            self._condition.notify_all()

    def _keep(self, message: dict[str, object]) -> None:
        method = message.get("method")
        number = message.get("id")
        if isinstance(method, str) and "id" not in message:
            self._notes.append(RpcNote(method, message.get("params")))
            return
        if not isinstance(number, int):
            return
        if "error" in message:
            self._errors[number] = _error_text(message.get("error"))
            return
        self._results[number] = message.get("result")

    def _mark_closed(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()

    def _debug(self) -> str:
        names = ", ".join(note.method for note in self._notes)
        return f"notifications: {names}"


def as_dict(value: object) -> dict[str, object] | None:
    """ Return ``value`` when it is a JSON object. """
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _pid() -> int:
    return os.getpid()


def _message_with(
    notes: list[RpcNote],
    method: str,
    needle: str,
) -> str | None:
    for message in _messages(notes, method):
        if needle in message:
            return message
    return None


def _messages(notes: list[RpcNote], method: str) -> list[str]:
    found: list[str] = []
    for note in notes:
        if note.method != method:
            continue
        payload = as_dict(note.params)
        if payload is None:
            continue
        message = payload.get("message")
        if isinstance(message, str):
            found.append(message)
    return found


def _diagnostics_for(note: RpcNote, uri: str) -> list[object] | None:
    if note.method != "textDocument/publishDiagnostics":
        return None
    payload = as_dict(note.params)
    if payload is None or payload.get("uri") != uri:
        return None
    items = payload.get("diagnostics")
    if isinstance(items, list):
        return cast(list[object], items)
    return None


def _error_text(value: object) -> str:
    record = as_dict(value)
    if record is None:
        return str(value)
    message = record.get("message")
    if isinstance(message, str):
        return message
    return str(value)


def _read_message(stream: BinaryIO) -> dict[str, object] | None:
    length = _header_length(stream)
    if length is None:
        return None
    body = _read_exact(stream, length)
    if body is None:
        return None
    decoded = cast(object, json.loads(body.decode("utf-8")))
    return as_dict(decoded)


def _header_length(stream: BinaryIO) -> int | None:
    length: int | None = None
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            return length
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":", 1)[1].strip())


def _read_exact(stream: BinaryIO, count: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = count
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
