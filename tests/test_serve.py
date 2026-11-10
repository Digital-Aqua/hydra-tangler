""" The language server over stdio. """

import json
import os
import subprocess
import threading
from collections.abc import Callable, Generator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, cast

from tests.books import fence
from tests.lsp_client import LspClient, as_dict

from hydra_tangler.check.lint import Runner
from hydra_tangler.serve.server import create_server

_PROJECT = Path(__file__).resolve().parents[1]


@contextmanager
def _process(
    root: Path,
) -> Generator[tuple[LspClient, subprocess.Popen[bytes]]]:
    proc = subprocess.Popen(
        ["uv", "run", "--project", str(_PROJECT), "hydra", "serve"],
        cwd=root,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdin, stdout, stderr = _stdio(proc)
    notes: list[str] = []
    drain = threading.Thread(
        target=_keep_text,
        args=(stderr, notes),
        daemon=True,
    )
    drain.start()
    client = LspClient(stdout, stdin)
    try:
        yield client, proc
    except Exception as err:
        err.add_note("".join(notes))
        err.add_note(client.debug())
        raise
    finally:
        client.close()
        _stop(proc)


@contextmanager
def _memory(root: Path, run: Runner) -> Generator[LspClient]:
    _ = root
    server_read, client_write = os.pipe()
    client_read, server_write = os.pipe()
    server = create_server(run)
    thread = threading.Thread(
        target=server.start_io,
        args=(os.fdopen(server_read, "rb"), os.fdopen(server_write, "wb")),
        daemon=True,
    )
    thread.start()
    client = LspClient(
        os.fdopen(client_read, "rb"),
        os.fdopen(client_write, "wb"),
    )
    try:
        yield client
    except Exception as err:
        err.add_note(client.debug())
        raise
    finally:
        client.close()
        thread.join(timeout=3)


def test_unclosed_fence_status_and_rebuild(tmp_path: Path) -> None:
    root = _project(tmp_path)
    uri = _chapter(root, "a.md")
    with _process(root) as (client, _proc):
        _ = client.initialize(root, write=False)
        client.open_markdown(uri, "ok\n```python\nx\n")
        busy = client.wait_status("busy")
        idle = client.wait_status("idle")
        items = client.wait_diagnostics(uri, _has("unclosed-fence"))
        rebuilt = as_dict(client.request("hydra/rebuild", {}))
    assert busy["state"] == "busy"
    assert busy["errors"] == 0
    assert idle["errors"] == 1
    assert idle["warnings"] == 0
    assert _line_of(items, "unclosed-fence") == 1
    assert rebuilt is not None
    assert rebuilt["errors"] == 1
    assert rebuilt["state"] == "idle"


def test_shutdown_then_exit_returns_zero(tmp_path: Path) -> None:
    root = _project(tmp_path)
    with _process(root) as (client, proc):
        _ = client.initialize(root, write=False)
        _ = client.request("shutdown", None)
        client.notify("exit", None)
        assert proc.wait(timeout=5) == 0


def test_dead_link_clears_after_did_change(tmp_path: Path) -> None:
    root = _project(tmp_path)
    _ = (root / "src" / "other.md").write_text("# Other\n", encoding="utf-8")
    uri = _chapter(root, "a.md")
    with _process(root) as (client, _proc):
        _ = client.initialize(root, write=False)
        client.open_markdown(uri, "See [gone](missing.md).\n")
        _ = client.wait_diagnostics(uri, _has("dead-link"))
        client.change_markdown(uri, "See [ok](other.md).\n", version=2)
        cleared = client.wait_diagnostics(uri, _empty)
    assert cleared == []


def test_stale_diagnostics_clear_without_wiping_another_file(
    tmp_path: Path,
) -> None:
    root = _project(tmp_path)
    broken = _chapter(root, "a.md")
    linked = _chapter(root, "b.md")
    with _process(root) as (client, _proc):
        _ = client.initialize(root, write=False)
        client.open_markdown(broken, "ok\n```python\nx\n")
        client.open_markdown(linked, "See [gone](missing.md).\n", version=1)
        _ = client.wait_diagnostics(broken, _has("unclosed-fence"))
        _ = client.wait_diagnostics(linked, _has("dead-link"))
        client.change_markdown(broken, "fine\n", version=2)
        cleared = client.wait_diagnostics(broken, _empty)
        still = client.wait_diagnostics(linked, _has("dead-link"))
    assert cleared == []
    assert "dead-link" in _codes(still)


def test_lint_findings_land_on_the_markdown_line(tmp_path: Path) -> None:
    root = _project(tmp_path)
    uri = _chapter(root, "c.md")
    text = fence("python file=m.py", "value = 1")
    with _memory(root, _finding) as client:
        _ = client.initialize(root, write=False)
        client.open_markdown(uri, text)
        code = "basedpyright:reportAssignmentType"
        items = client.wait_diagnostics(uri, _has(code))
    assert _line_of(items, code) == 1


def test_save_writes_the_open_buffer_when_asked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    uri = _chapter(root, "a.md")
    disk = root / "src" / "a.md"
    _ = disk.write_text(fence("python file=m.py", "old = 1"), encoding="utf-8")
    fresh = fence("python file=m.py", "new = 1")
    built = root / "_build" / "python" / "m.py"
    with _memory(root, _quiet) as client:
        _ = client.initialize(root, write=True)
        client.open_markdown(uri, fresh)
        _ = client.wait_status("idle")
        assert not built.exists()
        client.save_markdown(uri, fresh)
        _ = client.wait_status("idle")
    assert built.is_file()
    written = built.read_bytes()
    assert b"new = 1" in written
    assert b"old = 1" not in written


def test_hover_and_definition_follow_the_source_map(tmp_path: Path) -> None:
    root = _project(tmp_path)
    uri = _chapter(root, "a.md")
    text = fence(
        "python file=m.py",
        "def greet(name: str) -> str:",
        "    return name",
        "",
        "value = greet('x')",
    )
    with _memory(root, _quiet) as client:
        _ = client.initialize(root, write=False, pyright=_pyright_command())
        client.open_markdown(uri, text)
        _ = client.wait_status("idle")
        try:
            hover = client.request(
                "textDocument/hover",
                _cursor(uri, 4, 8),
                timeout=20,
            )
            defined = client.request(
                "textDocument/definition",
                _cursor(uri, 4, 8),
                timeout=10,
            )
            completed = client.request(
                "textDocument/completion",
                _cursor(uri, 4, 8),
                timeout=10,
            )
        finally:
            _ = client.request("shutdown", None, timeout=8)
    assert "greet" in json.dumps(hover)
    assert 1 in _target_lines(defined, uri)
    assert completed is not None


def test_save_does_not_write_unless_asked(tmp_path: Path) -> None:
    root = _project(tmp_path)
    uri = _chapter(root, "a.md")
    text = fence("python file=m.py", "value = 1")
    built = root / "_build" / "python" / "m.py"
    with _memory(root, _quiet) as client:
        _ = client.initialize(root, write=False)
        client.open_markdown(uri, text)
        _ = client.wait_status("idle")
        client.save_markdown(uri, text)
        _ = client.wait_status("idle")
    assert not built.exists()


def _pyright_command() -> tuple[str, ...]:
    return (
        "uv",
        "run",
        "--project",
        str(_PROJECT),
        "basedpyright-langserver",
        "--stdio",
    )


def _cursor(uri: str, line: int, character: int) -> dict[str, object]:
    return {
        "textDocument": {"uri": uri},
        "position": {"line": line, "character": character},
    }


def _target_lines(payload: object, uri: str) -> list[int]:
    found: list[int] = []
    for item in _records(payload):
        record = as_dict(item)
        if record is None or record.get("uri") != uri:
            continue
        line = _start_line(record.get("range"))
        if line is not None:
            found.append(line)
    return found


def _records(payload: object) -> list[object]:
    if isinstance(payload, list):
        return cast(list[object], payload)
    if payload is None:
        return []
    return [payload]


def _project(root: Path) -> Path:
    _ = (root / "src").mkdir()
    _ = (root / "pyproject.toml").write_text(
        '[tool.hydra]\noutputs = ["python"]\n',
        encoding="utf-8",
    )
    return root


def _chapter(root: Path, name: str) -> str:
    return (root / "src" / name).resolve().as_uri()


def _stdio(
    proc: subprocess.Popen[bytes],
) -> tuple[BinaryIO, BinaryIO, BinaryIO]:
    stdin = proc.stdin
    stdout = proc.stdout
    stderr = proc.stderr
    if stdin is None or stdout is None or stderr is None:
        raise RuntimeError("hydra serve did not pipe stdio")
    return cast(BinaryIO, stdin), cast(BinaryIO, stdout), cast(BinaryIO, stderr)


def _stop(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    proc.kill()
    _ = proc.wait(timeout=3)


def _keep_text(stream: BinaryIO, notes: list[str]) -> None:
    notes.append(stream.read().decode("utf-8", errors="replace"))


def _quiet(argv: Sequence[str], cwd: Path) -> str:
    _ = cwd
    if _tool(argv) == "ruff":
        return "[]"
    return json.dumps({"generalDiagnostics": []})


def _finding(argv: Sequence[str], cwd: Path) -> str:
    _ = cwd
    if _tool(argv) != "basedpyright":
        return "[]"
    payload = {
        "generalDiagnostics": [
            {
                "file": argv[-1],
                "severity": "error",
                "message": "bad type",
                "rule": "reportAssignmentType",
                "range": {"start": {"line": 1, "character": 0}},
            }
        ]
    }
    return json.dumps(payload)


def _tool(argv: Sequence[str]) -> str:
    for word in argv:
        name = Path(word).name
        if name in ("basedpyright", "ruff"):
            return name
    return ""


def _has(code: str) -> Callable[[list[object]], bool]:
    def match(items: list[object]) -> bool:
        return code in _codes(items)

    return match


def _empty(items: list[object]) -> bool:
    return items == []


def _codes(items: list[object]) -> list[str]:
    found: list[str] = []
    for item in items:
        record = as_dict(item)
        if record is None:
            continue
        code = record.get("code")
        if isinstance(code, str):
            found.append(code)
    return found


def _line_of(items: list[object], code: str) -> int | None:
    for item in items:
        record = as_dict(item)
        if record is None or record.get("code") != code:
            continue
        return _start_line(record.get("range"))
    return None


def _start_line(value: object) -> int | None:
    span = as_dict(value)
    if span is None:
        return None
    start = as_dict(span.get("start"))
    if start is None:
        return None
    line = start.get("line")
    if isinstance(line, int):
        return line
    return None
