""" One basedpyright language server, spoken to over stdio.

The process starts on the first query. The caller pushes Python
file text with ``didOpen`` and full ``didChange`` notifications.
``workspace/configuration`` is answered with nulls. Stderr is kept
as a short tail so a failed start can name the last line. This
module does not translate Markdown positions.
"""

import json
import os
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, cast, final

_STDERR_TAIL = 8

_START_TIMEOUT = 8.0
_REQUEST_TIMEOUT = 5.0


def default_command(project: Path) -> tuple[str, ...]:
    """ The ``uv run`` invocation for this project's basedpyright. """
    return (
        "uv",
        "run",
        "--project",
        str(project),
        "basedpyright-langserver",
        "--stdio",
    )


@final
class PyrightServer:
    """ A running ``basedpyright-langserver --stdio``. """

    def __init__(self, command: tuple[str, ...], shadow: Path) -> None:
        self._command = command
        self._shadow = shadow
        self._lock = threading.Lock()
        self._condition = threading.Condition()
        self._results: dict[int | str, object] = {}
        self._errors: set[int | str] = set()
        self._next = 1
        self._closed = False
        self._stdin: BinaryIO | None = None
        self._process: subprocess.Popen[bytes] | None = None
        self._thread: threading.Thread | None = None
        self._stderr_thread: threading.Thread | None = None
        self._stderr: deque[str] = deque(maxlen=_STDERR_TAIL)
        self._failure = ""
        self._request_failed = False

    def start(self) -> bool:
        """ Spawn the process and finish its initialize handshake. """
        if not self._spawn():
            return False
        started = self.request(
            "initialize",
            _initialize(self._shadow),
            timeout=_START_TIMEOUT,
        )
        if self.request_failed() or started is None:
            self._remember("basedpyright handshake failed")
            self.stop()
            return False
        self.notify("initialized", {})
        return True

    def request_failed(self) -> bool:
        """ Whether the last ``request`` failed rather than returning. """
        return self._request_failed

    def failure_detail(self) -> str:
        """ Why the server failed, including the last stderr line. """
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
        """ Send a request and return its result, or None on failure. """
        self._request_failed = False
        number = self._send_request(method, params)
        if number is None:
            self._request_failed = True
            self._remember("basedpyright language server is not running")
            return None
        return self._wait(number, timeout)

    def notify(self, method: str, params: object) -> None:
        """ Send a notification. A dead process is ignored. """
        self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def stop(self) -> None:
        """ Kill the process group and wait for the reader to finish. """
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
        """ Return whether the process has stopped. """
        process = self._process
        return process is None or process.poll() is not None

    def _spawn(self) -> bool:
        try:
            process = self._open()
        except OSError as err:
            reason = err.strerror or str(err)
            self._remember(f"cannot start basedpyright: {reason}")
            return False
        return self._attach(process)

    def _open(self) -> subprocess.Popen[bytes]:
        self._shadow.mkdir(parents=True, exist_ok=True)
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
        number = _message_id(message.get("id"))
        if isinstance(method, str) and number is not None:
            self._answer(number, method, message.get("params"))
            return
        if number is not None and "method" not in message:
            self._store(number, message)

    def _answer(self, number: int | str, method: str, params: object) -> None:
        if method == "workspace/configuration":
            result: object = _nulls(params)
        else:
            result = None
        self._send({"jsonrpc": "2.0", "id": number, "result": result})

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
        """ Record a failed request. The caller holds ``_condition``. """
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


def _initialize(shadow: Path) -> dict[str, object]:
    uri = shadow.resolve().as_uri()
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
        "workspaceFolders": [{"uri": uri, "name": "hydra-shadow"}],
    }


def _nulls(params: object) -> list[None]:
    record = _as_dict(params)
    if record is None:
        return []
    items = record.get("items")
    if isinstance(items, list):
        return [None] * len(cast(list[object], items))
    return []


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
