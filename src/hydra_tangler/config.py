""" Read ``[tool.hydra]`` from ``pyproject.toml``.

The source directory, selected output names, and checker commands
are read. Missing files and a missing table mean "use the defaults".
This module does not discover Markdown or run outputs.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import cast


class ConfigError(Exception):
    """ ``[tool.hydra]`` is present but not usable. """


@dataclass(frozen=True)
class CheckSettings:
    """ Argv overrides from ``[tool.hydra.check]``.

    An empty command means the caller builds the default ``uv run``
    invocation for that checker.
    """

    pyright: tuple[str, ...] = ()
    ruff: tuple[str, ...] = ()


@dataclass(frozen=True)
class HydraConfig:
    """ Settings from ``[tool.hydra]``.

    ``source`` is None when the table does not set one, so the caller
    falls back to the default source directory. An empty ``outputs``
    means every registered output.
    """

    source: Path | None = None
    outputs: tuple[str, ...] = ()
    check: CheckSettings = CheckSettings()


def load_config(cwd: Path) -> HydraConfig:
    """ Read ``cwd/pyproject.toml``. Return defaults when it is absent. """
    path = cwd / "pyproject.toml"
    if not path.is_file():
        return HydraConfig()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    table = _hydra_table(data)
    if table is None:
        return HydraConfig()
    return HydraConfig(_source(table), _outputs(table), _check(table))


def _hydra_table(data: object) -> dict[str, object] | None:
    root = _as_dict(data)
    if root is None:
        return None
    tool = root.get("tool")
    if tool is None:
        return None
    tool_table = _as_dict(tool)
    if tool_table is None:
        raise ConfigError("[tool.hydra] must be a table")
    table = tool_table.get("hydra")
    if table is None:
        return None
    hydra = _as_dict(table)
    if hydra is None:
        raise ConfigError("[tool.hydra] must be a table")
    return hydra


def _as_dict(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return cast(dict[str, object], value)
    return None


def _source(table: dict[str, object]) -> Path | None:
    raw = table.get("source")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw:
        raise ConfigError("[tool.hydra] source must be a string")
    return Path(raw)


def _outputs(table: dict[str, object]) -> tuple[str, ...]:
    raw = table.get("outputs")
    if raw is None:
        return ()
    items = _as_list(raw)
    if items is None:
        raise ConfigError("[tool.hydra] outputs must be an array of strings")
    names: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise ConfigError(
                "[tool.hydra] outputs must be an array of strings"
            )
        names.append(item)
    return tuple(names)


def _check(table: dict[str, object]) -> CheckSettings:
    raw = table.get("check")
    if raw is None:
        return CheckSettings()
    check = _as_dict(raw)
    if check is None:
        raise ConfigError("[tool.hydra.check] must be a table")
    return CheckSettings(
        _argv(check, "pyright"),
        _argv(check, "ruff"),
    )


def _argv(table: dict[str, object], key: str) -> tuple[str, ...]:
    raw = table.get(key)
    if raw is None:
        return ()
    items = _as_list(raw)
    if items is None:
        raise ConfigError(
            f"[tool.hydra.check] {key} must be an array of strings"
        )
    words: list[str] = []
    for item in items:
        if not isinstance(item, str) or not item:
            raise ConfigError(
                f"[tool.hydra.check] {key} must be an array of strings"
            )
        words.append(item)
    return tuple(words)


def _as_list(value: object) -> list[object] | None:
    if isinstance(value, list):
        return cast(list[object], value)
    return None
