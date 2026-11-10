""" Read the language server's initialization options.

``write`` controls whether a save tangles to the build directory.
``pyrightCommand`` replaces the basedpyright language server argv.
Unknown keys are ignored. This module does not start a process.
"""

from dataclasses import dataclass
from typing import cast


@dataclass(frozen=True)
class ServeOptions:
    """ Client choices read from ``initializationOptions``.

    ``pyright`` is empty when the client did not name a command, and
    the server then uses its default ``uv run`` invocation.
    """

    write: bool = False
    pyright: tuple[str, ...] = ()


def read_options(raw: object) -> ServeOptions:
    """ Return options from ``initializationOptions``, or the defaults. """
    table = _as_dict(raw)
    if table is None:
        return ServeOptions()
    return ServeOptions(
        write=table.get("write") is True,
        pyright=_command(table.get("pyrightCommand")),
    )


def _command(value: object) -> tuple[str, ...]:
    items = _as_list(value)
    if not items:
        return ()
    words: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item:
            return ()
        words.append(item)
    return tuple(words)


def _as_list(value: object) -> list[object]:
    if isinstance(value, list):
        return cast(list[object], value)
    return []


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None
