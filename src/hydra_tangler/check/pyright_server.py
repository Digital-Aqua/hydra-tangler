"""One basedpyright language server for diagnostics and navigation.

The process is the basedpyright shipped with Hydra. Its workspace
root is the book, so a ``.venv`` there is the interpreter, and the
tangled files under ``.hydra/shadow`` are opened into that program.
``workspace/configuration`` names that interpreter and points at the
merged config from ``defaults.py``. Hover, definition, completion,
and ``publishDiagnostics`` all come from this process. This module
does not translate Markdown positions.
"""

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Protocol, cast, final

from hydra_tangler.check.defaults import basedpyright_config
from hydra_tangler.check.errors import LintError

_STDERR_TAIL = 8
_START_TIMEOUT = 8.0
_REQUEST_TIMEOUT = 5.0
_CONFIG_TIMEOUT = 2.0
_DIAGNOSTIC_TIMEOUT = 10.0
def bundled_command() -> tuple[str, ...]:
    """``basedpyright-langserver`` beside the interpreter running Hydra."""
    binary = Path(sys.executable).with_name("basedpyright-langserver")
    return (str(binary), "--stdio")


def configuration_result(
    book: Path,
    items: Sequence[object],
) -> list[object]:
    """Settings for one ``workspace/configuration`` request.

    The interpreter is ``<book>/.venv/bin/python`` when that file
    exists. Analysis settings come from the merged config file.
    """
    return [_section(book, item) for item in items]


def initialize_params(book: Path) -> dict[str, object]:
    """LSP ``initialize`` params rooted at ``book``."""
    uri = book.resolve().as_uri()
    return {
        "processId": os.getpid(),
        "rootUri": uri,
        "capabilities": {
            "workspace": {"configuration": True},
            "textDocument": {
                "hover": {},
                "definition": {},
                "completion": {},
            },
        },
        "workspaceFolders": [{"uri": uri, "name": "book"}],
    }


@dataclass(frozen=True)
class TypeReport:
    """One basedpyright diagnostic, still on a shadow file.

    Lines and characters are 0-based, as the language server sends them.
    """

    file: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int
    severity: str
    rule: str
    message: str


def parse_type_diagnostic(uri: str, item: object) -> TypeReport | None:
    """Read one language-server diagnostic. ``None`` when it is unusable."""
    return _report(uri, item)


class TypeChecker(Protocol):
    """Produce type diagnostics for one tangled snapshot."""

    def check(
        self,
        book: Path,
        shadow: Path,
        files: Mapping[Path, str],
    ) -> tuple[TypeReport, ...]:
        """Return findings for ``files`` (shadow path to text)."""
        raise NotImplementedError


@final
class BasedpyrightCheck:
    """The type checker backed by one ``PyrightServer``."""

    def __init__(self, command: tuple[str, ...], book: Path) -> None:
        argv = command if command else bundled_command()
        self.server: PyrightServer = PyrightServer(argv, book)

    def check(
        self,
        book: Path,
        shadow: Path,
        files: Mapping[Path, str],
    ) -> tuple[TypeReport, ...]:
        """Open ``files`` and wait for their diagnostics."""
        _ = book
        server = self.server
        if not server.ensure_started():
            _ = server.claim_failure()
            raise LintError(server.failure_detail())
        server.sync(shadow, files)
        return server.wait_reports(shadow, tuple(files))

    def close(self) -> None:
        """Stop the language server."""
        self.server.stop()


@dataclass(frozen=True)
class _Publication:
    version: int | None
    reports: tuple[TypeReport, ...]


@final
class PyrightServer:
    """A running ``basedpyright-langserver --stdio``."""

    def __init__(self, command: tuple[str, ...], book: Path) -> None:
        self._command = command
        self._book = book
        self._shadow = book
        self._lock = threading.Lock()
        self._start_lock = threading.Lock()
        self._condition = threading.Condition()
        self._results: dict[int | str, object] = {}
        self._errors: set[int | str] = set()
        self._next = 1
        self._closed = False
        self._up = False
        self._configured = False
        self._claimed = False
        self._stdin: BinaryIO | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr: deque[str] = deque(maxlen=_STDERR_TAIL)
        self._failure = ""
        self._request_failed = False
        self._opened: set[Path] = set()
        self._text: dict[Path, str] = {}
        self._version: dict[Path, int] = {}
        self._published: dict[str, _Publication] = {}

    def ensure_started(self) -> bool:
        """Start the process once. Further calls reuse it."""
        with self._start_lock:
            if self._up:
                return not self._failure
            if self._closed and self._process is not None:
                return False
            if not self.start():
                return False
            self._up = True
        self._wait_configured()
        if not self._failure:
            return True
        with self._start_lock:
            self._up = False
        return False

    def start(self) -> bool:
        """Spawn the process and finish its initialize handshake."""
        if not self._spawn():
            return False
        started = self.request(
            "initialize",
            initialize_params(self._book),
            timeout=_START_TIMEOUT,
        )
        if self.request_failed() or started is None:
            self._remember("basedpyright handshake failed")
            self.stop()
            return False
        self.notify("initialized", {})
        return True

    def sync(self, shadow: Path, files: Mapping[Path, str]) -> None:
        """Open, change, or close tangled files to match ``files``."""
        self._shadow = shadow.resolve()
        current = set(files)
        for path in list(self._opened):
            if path not in current:
                self._close(path)
        for path, text in files.items():
            self._sync_one(path, text)

    def wait_reports(
        self,
        shadow: Path,
        paths: tuple[Path, ...],
        timeout: float = _DIAGNOSTIC_TIMEOUT,
    ) -> tuple[TypeReport, ...]:
        """Block until each path has diagnostics for its current version."""
        self._shadow = shadow.resolve()
        wanted = tuple(self._uri(path) for path in paths)
        versions = tuple(self._version.get(path, 1) for path in paths)
        return self._wait_published(wanted, versions, timeout)

    def claim_failure(self) -> str | None:
        """The failure text, once. A second caller gets ``None``."""
        with self._condition:
            if not self._failure or self._claimed:
                return None
            self._claimed = True
            return self.failure_detail()

    def request_failed(self) -> bool:
        """Whether the last ``request`` failed rather than returning."""
        return self._request_failed

    def failure_detail(self) -> str:
        """Why the server failed, including the last stderr line."""
        reason = self._failure or "basedpyright language server failed"
        last = self._last_stderr()
        if not last:
            return reason
        return f"{reason}: {last}"

    def request(
        self,
        method: str,
        params: object,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> object | None:
        """Send a request and return its result, or None on failure."""
        self._request_failed = False
        number = self._send_request(method, params)
        if number is None:
            self._request_failed = True
            self._remember("basedpyright language server is not running")
            return None
        return self._wait(number, timeout)

    def notify(self, method: str, params: object) -> None:
        """Send a notification. A dead process is ignored."""
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def stop(self) -> None:
        """Kill the process group and wait for the reader to finish."""
        process = self._process
        self._mark_closed()
        if process is None:
            return
        _kill(process)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2)
        stderr = self._stderr_thread
        if stderr is not None:
            stderr.join(timeout=1)

    def exited(self) -> bool:
        """Return whether the process has stopped."""
        process = self._process
        return process is None or process.poll() is not None

    def _sync_one(self, path: Path, text: str) -> None:
        uri = self._uri(path)
        if path not in self._opened:
            self._version[path] = 1
            self._text[path] = text
            self._opened.add(path)
            self.notify("textDocument/didOpen", _opened(uri, text, 1))
            return
        if self._text.get(path) == text:
            return
        version = self._version.get(path, 1) + 1
        self._version[path] = version
        self._text[path] = text
        self.notify("textDocument/didChange", _changed(uri, text, version))

    def _close(self, path: Path) -> None:
        self.notify(
            "textDocument/didClose",
            {"textDocument": {"uri": self._uri(path)}},
        )
        uri = self._uri(path)
        self._opened.discard(path)
        _ = self._text.pop(path, None)
        _ = self._version.pop(path, None)
        with self._condition:
            _ = self._published.pop(uri, None)

    def _uri(self, path: Path) -> str:
        return (self._shadow / path).resolve().as_uri()

    def _wait_configured(self) -> None:
        deadline = time.monotonic() + _CONFIG_TIMEOUT
        with self._condition:
            while not self._configured and not self._closed:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                _ = self._condition.wait(remaining)

    def _wait_published(
        self,
        uris: tuple[str, ...],
        versions: tuple[int, ...],
        timeout: float,
    ) -> tuple[TypeReport, ...]:
        deadline = time.monotonic() + timeout
        reason = ""
        with self._condition:
            while not _fresh(self._published, uris, versions):
                if self._closed:
                    reason = self._failure or "basedpyright exited"
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    reason = ""
                    break
                _ = self._condition.wait(remaining)
            else:
                return _reports(self._published, uris)
        if not reason:
            raise LintError("basedpyright produced no diagnostics")
        last = self._last_stderr()
        if last:
            reason = f"{reason}: {last}"
        raise LintError(reason)

    def _spawn(self) -> bool:
        try:
            process = self._open()
        except OSError as err:
            reason = err.strerror or str(err)
            self._remember(f"cannot start basedpyright: {reason}")
            return False
        return self._attach(process)

    def _open(self) -> subprocess.Popen[bytes]:
        return subprocess.Popen(
            list(self._command),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )

    def _attach(self, process: subprocess.Popen[bytes]) -> bool:
        stdin = process.stdin
        stdout = process.stdout
        stderr = process.stderr
        if stdin is None or stdout is None or stderr is None:
            process.kill()
            self._remember("basedpyright stdio was not available")
            return False
        self._process = process
        self._stdin = cast(BinaryIO, stdin)
        self._thread = self._daemon(self._read_loop, cast(BinaryIO, stdout))
        self._stderr_thread = self._daemon(
            self._read_stderr,
            cast(BinaryIO, stderr),
        )
        return True

    def _daemon(
        self,
        target: Callable[[BinaryIO], None],
        stream: BinaryIO,
    ) -> threading.Thread:
        thread = threading.Thread(
            target=target,
            args=(stream,),
            daemon=True,
        )
        thread.start()
        return thread

    def _send_request(self, method: str, params: object) -> int | None:
        with self._lock:
            if self._stdin is None:
                return None
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
        return number

    def _send(self, payload: dict[str, object]) -> None:
        raw = json.dumps(payload).encode("utf-8")
        packet = f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii") + raw
        if not self._write(packet):
            self._mark_closed()

    def _write(self, packet: bytes) -> bool:
        with self._lock:
            stdin = self._stdin
            if stdin is None:
                return False
            try:
                _ = stdin.write(packet)
                stdin.flush()
            except OSError:
                self._stdin = None
                return False
        return True

    def _wait(self, number: int | str, timeout: float) -> object | None:
        deadline = time.monotonic() + timeout
        with self._condition:
            while number not in self._results and number not in self._errors:
                if self._closed:
                    self._fail_locked("basedpyright language server exited")
                    return None
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._fail_locked("basedpyright request timed out")
                    return None
                _ = self._condition.wait(remaining)
            if number in self._errors:
                self._fail_locked("basedpyright request failed")
                return None
            self._failure = ""
            self._request_failed = False
            return self._results.get(number)

    def _read_loop(self, stdout: BinaryIO) -> None:
        while True:
            message = _read_message(stdout)
            if message is None:
                self._mark_closed()
                return
            self._dispatch(message)

    def _dispatch(self, message: dict[str, object]) -> None:
        method = message.get("method")
        if method == "textDocument/publishDiagnostics":
            self._store_diagnostics(message.get("params"))
            return
        number = _message_id(message.get("id"))
        if isinstance(method, str) and number is not None:
            self._answer(number, method, message.get("params"))
            return
        if number is not None and "method" not in message:
            self._store(number, message)

    def _answer(self, number: int | str, method: str, params: object) -> None:
        if method == "workspace/configuration":
            result = self._configuration(params)
            self._mark_configured()
        else:
            result = None
        self._send({"jsonrpc": "2.0", "id": number, "result": result})

    def _configuration(self, params: object) -> list[object]:
        try:
            return _configuration(self._book, params)
        except LintError as err:
            self._remember(str(err))
            return []

    def _mark_configured(self) -> None:
        with self._condition:
            self._configured = True
            self._condition.notify_all()

    def _store_diagnostics(self, params: object) -> None:
        record = _as_dict(params)
        if record is None:
            return
        uri = record.get("uri")
        items = record.get("diagnostics")
        if not isinstance(uri, str) or not isinstance(items, list):
            return
        version = record.get("version")
        published = _Publication(
            version if isinstance(version, int) else None,
            _keep(uri, cast(list[object], items)),
        )
        with self._condition:
            self._published[uri] = published
            self._condition.notify_all()

    def _store(self, number: int | str, message: dict[str, object]) -> None:
        with self._condition:
            if "error" in message:
                self._errors.add(number)
            else:
                self._results[number] = message.get("result")
            self._condition.notify_all()

    def _mark_closed(self) -> None:
        with self._condition:
            if not self._failure:
                self._failure = "basedpyright language server exited"
            self._closed = True
            self._condition.notify_all()

    def _remember(self, text: str) -> None:
        with self._condition:
            if not self._failure:
                self._failure = text

    def _fail_locked(self, text: str) -> None:
        """Record a failed request. The caller holds ``_condition``."""
        self._request_failed = True
        if not self._failure:
            self._failure = text

    def _last_stderr(self) -> str:
        with self._lock:
            if not self._stderr:
                return ""
            return self._stderr[-1]

    def _read_stderr(self, stream: BinaryIO) -> None:
        for raw in iter(stream.readline, b""):
            text = raw.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            with self._lock:
                self._stderr.append(text)


def _section(book: Path, item: object) -> object:
    record = _as_dict(item)
    section = record.get("section") if record is not None else None
    if section == "python":
        return _python_section(book)
    if section == "basedpyright":
        return _analysis_section(book)
    return None


def _python_section(book: Path) -> dict[str, object]:
    python = book / ".venv" / "bin" / "python"
    if python.is_file():
        return {"pythonPath": str(python)}
    return {}


def _analysis_section(book: Path) -> dict[str, object]:
    return {
        "analysis": {
            "diagnosticMode": "openFilesOnly",
            "configFilePath": str(basedpyright_config(book)),
        }
    }


def _configuration(book: Path, params: object) -> list[object]:
    record = _as_dict(params)
    if record is None:
        return []
    items = record.get("items")
    if not isinstance(items, list):
        return []
    return configuration_result(book, cast(list[object], items))


def _fresh(
    published: dict[str, _Publication],
    uris: tuple[str, ...],
    versions: tuple[int, ...],
) -> bool:
    for uri, version in zip(uris, versions, strict=True):
        found = published.get(uri)
        if found is None:
            return False
        if found.version is not None and found.version < version:
            return False
    return True


def _reports(
    published: dict[str, _Publication],
    uris: tuple[str, ...],
) -> tuple[TypeReport, ...]:
    found: list[TypeReport] = []
    for uri in uris:
        item = published.get(uri)
        if item is not None:
            found.extend(item.reports)
    return tuple(found)


def _keep(uri: str, items: list[object]) -> tuple[TypeReport, ...]:
    found: list[TypeReport] = []
    for item in items:
        report = _report(uri, item)
        if report is not None:
            found.append(report)
    return tuple(found)


def _report(uri: str, item: object) -> TypeReport | None:
    record = _as_dict(item)
    if record is None:
        return None
    severity = _severity(record.get("severity"))
    span = _span(record.get("range"))
    if severity is None or span is None:
        return None
    rule = record.get("code")
    return TypeReport(
        uri,
        span[0],
        span[1],
        span[2],
        span[3],
        severity,
        rule if isinstance(rule, str) else "",
        _message(record.get("message")),
    )


def _span(value: object) -> tuple[int, int, int, int] | None:
    record = _as_dict(value)
    if record is None:
        return None
    start = _point(record.get("start"))
    end = _point(record.get("end"))
    if start is None:
        return None
    if end is None:
        return (start[0], start[1], start[0], start[1])
    return (start[0], start[1], end[0], end[1])


def _point(value: object) -> tuple[int, int] | None:
    record = _as_dict(value)
    if record is None:
        return None
    line = record.get("line")
    character = record.get("character", 0)
    if isinstance(line, bool) or isinstance(character, bool):
        return None
    if not isinstance(line, int) or not isinstance(character, int):
        return None
    return (line, character)


def _severity(value: object) -> str | None:
    if value in (1, "error"):
        return "error"
    if value in (2, "warning", 3, "information", 4, "hint"):
        return "warning"
    return None


def _message(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _opened(uri: str, text: str, version: int) -> dict[str, object]:
    return {
        "textDocument": {
            "uri": uri,
            "languageId": "python",
            "version": version,
            "text": text,
        }
    }


def _changed(uri: str, text: str, version: int) -> dict[str, object]:
    return {
        "textDocument": {"uri": uri, "version": version},
        "contentChanges": [{"text": text}],
    }


def _kill(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except OSError:
        process.kill()
    try:
        _ = process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except OSError:
            process.kill()
        _ = process.wait(timeout=2)


def _read_message(stream: BinaryIO) -> dict[str, object] | None:
    length = _header_length(stream)
    if length is None:
        return None
    body = _read_exact(stream, length)
    if body is None:
        return None
    try:
        decoded = cast(object, json.loads(body.decode("utf-8")))
    except json.JSONDecodeError:
        return None
    return _as_dict(decoded)


def _header_length(stream: BinaryIO) -> int | None:
    length: int | None = None
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            return length
        if line.lower().startswith(b"content-length:"):
            try:
                length = int(line.split(b":", 1)[1].strip())
            except ValueError:
                return None


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


def _message_id(value: object) -> int | str | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | str):
        return value
    return None


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None
