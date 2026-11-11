""" Read the language server's initialization options.

``write`` controls whether a save tangles to the build directory.
``pyrightCommand`` replaces the basedpyright checker argv.
``pyrightServerCommand`` replaces the basedpyright language-server
argv. ``ruffCommand`` replaces the ruff checker argv. A command that
is present but not a list of non-empty strings is rejected and the
default argv is kept. Unknown keys are ignored. This module does not
start a process or show a message; the caller reports ``rejected``.
"""

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class ServeOptions:
    """ Client choices read from ``initializationOptions``.

    ``pyright`` is the checker argv and ``pyright_server`` is the
    language-server argv. Each is empty when the client did not send
    a command, and the server then uses its default ``uv run``
    invocation. ``ruff`` is the same for the ruff checker.
    ``rejected`` names commands that were present and unusable.
    """

    write: bool = False
    pyright: tuple[str, ...] = ()
    pyright_server: tuple[str, ...] = ()
    ruff: tuple[str, ...] = ()
    rejected: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Parsed:
    """ One command argv, or the reason it was rejected. """

    argv: tuple[str, ...]
    rejected: str | None


def read_options(raw: object) -> ServeOptions:
    """ Return options from ``initializationOptions``, or the defaults. """
    table = _as_dict(raw)
    if table is None:
        return ServeOptions()
    pyright = _named(table, "pyrightCommand")
    server = _named(table, "pyrightServerCommand")
    ruff = _named(table, "ruffCommand")
    return ServeOptions(
        write=table.get("write") is True,
        pyright=pyright.argv,
        pyright_server=server.argv,
        ruff=ruff.argv,
        rejected=_rejected((pyright, server, ruff)),
    )


def _named(table: dict[str, object], name: str) -> _Parsed:
    if name not in table:
        return _Parsed((), None)
    return _command(name, table[name])


def _command(name: str, value: object) -> _Parsed:
    items = _as_list(value)
    if items is None:
        return _Parsed((), _bad(name))
    words: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item:
            return _Parsed((), _bad(name))
        words.append(item)
    return _Parsed(tuple(words), None)


def _bad(name: str) -> str:
    return (
        f"bad-checker-command: {name} must be a list of non-empty strings"
    )


def _rejected(parsed: tuple[_Parsed, ...]) -> tuple[str, ...]:
    return tuple(
        item.rejected for item in parsed if item.rejected is not None
    )


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None
