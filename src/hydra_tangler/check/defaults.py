"""Default ruff and basedpyright settings for a tangled book.

The defaults sit underneath the book's own configuration. For ruff,
Hydra writes a config that the book's ruff files extend, so a later
``extend-select`` of one code turns that rule back on and a later
``select`` replaces the rule set. For basedpyright, Hydra writes one
merged config: a book value replaces the default for that key and
leaves the other keys. This module does not run either checker.

Generated files are written under ``<book>/.hydra``. User-level ruff
config is not read. A book file that cannot be parsed is a
``LintError``.
"""

import json
import re
import tomllib
from pathlib import Path
from typing import cast

from hydra_tangler.check.errors import LintError

_RUFF_IGNORE = ("I001", "RUF100")
_PYRIGHT_MODE = "recommended"
_PYRIGHT_IGNORED = "reportUnnecessaryTypeIgnoreComment"
_SHADOW = ".hydra/shadow"
_GENERATED = ".hydra"
_RUFF_NAMES = (".ruff.toml", "ruff.toml")
_PATH_KEYS = frozenset(
    {
        "exclude",
        "extend-exclude",
        "include",
        "extend-include",
        "src",
        "cache-dir",
    }
)
_PYRIGHT_PATHS = frozenset(
    {
        "include",
        "exclude",
        "ignore",
        "extraPaths",
        "stubPath",
        "venvPath",
        "typeshedPath",
        "baselineFile",
        "root",
    }
)
_KEY = re.compile(r"[A-Za-z0-9_-]+")


def ruff_config_args(project: Path) -> tuple[str, ...]:
    """``--config`` for the generated file ruff should read."""
    directory = project / _GENERATED / "ruff"
    directory.mkdir(parents=True, exist_ok=True)
    base = directory / "defaults.toml"
    _write(base, _default_ruff())
    found = _find_ruff(project)
    if found is None:
        return ("--config", str(base))
    previous = base
    for index, source in enumerate(_ruff_chain(found)):
        target = directory / f"{index}.toml"
        _write(target, _ruff_layer(source, previous))
        previous = target
    return ("--config", str(previous))


def basedpyright_config(project: Path) -> Path:
    """Write the merged basedpyright config and return its path.

    The shadow tree stays on ``include`` so tangled files are part of
    the program even when the book lists its own roots.
    """
    shadow = str((project / _SHADOW).resolve())
    merged = _pyright_defaults(shadow)
    found = _find_pyright(project)
    if found is not None:
        merged = _overlay(merged, _pyright_chain(found))
    _keep_shadow(merged, shadow)
    path = project / _GENERATED / "pyrightconfig.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    _write(path, json.dumps(merged, indent=2) + "\n")
    return path


def _default_ruff() -> str:
    codes = ", ".join(_toml_string(code) for code in _RUFF_IGNORE)
    return f"[lint]\nignore = [{codes}]\n"


def _pyright_defaults(shadow: str) -> dict[str, object]:
    return {
        "include": [shadow],
        "typeCheckingMode": _PYRIGHT_MODE,
        _PYRIGHT_IGNORED: "none",
    }


def _find_ruff(project: Path) -> Path | None:
    for directory in (project, *project.parents):
        found = _ruff_in(directory)
        if found is not None:
            return found
    return None


def _ruff_in(directory: Path) -> Path | None:
    for name in _RUFF_NAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file() and _ruff_table(pyproject) is not None:
        return pyproject
    return None


def _ruff_chain(path: Path) -> tuple[Path, ...]:
    """Project files from the extend root down to ``path``."""
    seen: list[Path] = []
    stack: list[Path] = []
    current = path
    while True:
        resolved = current.resolve()
        if resolved in seen:
            raise LintError(f"ruff config extends itself: {current}")
        seen.append(resolved)
        stack.append(current)
        parent = _extend_target(current)
        if parent is None:
            break
        current = parent
    return tuple(reversed(stack))


def _extend_target(path: Path) -> Path | None:
    extend = _ruff_document(path).get("extend")
    if extend is None:
        return None
    if not isinstance(extend, str):
        raise LintError(f"{path} extend is not a string")
    target = Path(extend)
    if not target.is_absolute():
        target = path.parent / target
    if not target.is_file():
        raise LintError(f"{path} extends missing {target}")
    return target


def _ruff_layer(source: Path, previous: Path) -> str:
    document = _ruff_document(source)
    _ = document.pop("extend", None)
    rooted = _absolute_paths(document, source.parent)
    rooted = {"extend": str(previous.resolve()), **rooted}
    return _toml(rooted)


def _ruff_table(path: Path) -> dict[str, object] | None:
    tool = _toml_file(path).get("tool")
    if not isinstance(tool, dict):
        return None
    ruff = cast(dict[str, object], tool).get("ruff")
    if not isinstance(ruff, dict):
        return None
    return cast(dict[str, object], ruff)


def _ruff_document(path: Path) -> dict[str, object]:
    if path.name != "pyproject.toml":
        return _toml_file(path)
    table = _ruff_table(path)
    if table is None:
        raise LintError(f"{path} has no [tool.ruff] table")
    return dict(table)


def _find_pyright(project: Path) -> Path | None:
    candidate = project / "pyrightconfig.json"
    if candidate.is_file():
        return candidate
    pyproject = project / "pyproject.toml"
    if pyproject.is_file() and _pyright_table(pyproject) is not None:
        return pyproject
    return None


def _pyright_chain(path: Path) -> dict[str, object]:
    return _pyright_file(path, [])


def _pyright_file(path: Path, seen: list[Path]) -> dict[str, object]:
    resolved = path.resolve()
    if resolved in seen:
        raise LintError(f"basedpyright config extends itself: {path}")
    document = _pyright_paths(_pyright_document(path), path.parent)
    extends = document.pop("extends", None)
    if extends is None:
        return document
    if not isinstance(extends, str):
        raise LintError(f"{path} extends is not a string")
    parent = _resolve_extend(path, extends)
    base = _pyright_file(parent, [*seen, resolved])
    return _overlay(base, document)


def _pyright_document(path: Path) -> dict[str, object]:
    if path.name == "pyproject.toml":
        table = _pyright_table(path)
        if table is None:
            raise LintError(f"{path} has no basedpyright table")
        return dict(table)
    return _json_file(path)


def _pyright_table(path: Path) -> dict[str, object] | None:
    tool = _toml_file(path).get("tool")
    if not isinstance(tool, dict):
        return None
    table = cast(dict[str, object], tool)
    based = table.get("basedpyright")
    pyright = table.get("pyright")
    if isinstance(based, dict) and isinstance(pyright, dict):
        raise LintError(f"{path} has both basedpyright and pyright tables")
    if isinstance(based, dict):
        return cast(dict[str, object], based)
    if isinstance(pyright, dict):
        return cast(dict[str, object], pyright)
    return None


def _pyright_paths(
    document: dict[str, object],
    root: Path,
) -> dict[str, object]:
    rewritten: dict[str, object] = {}
    for key, value in document.items():
        rewritten[key] = _pyright_value(key, value, root)
    return rewritten


def _pyright_value(key: str, value: object, root: Path) -> object:
    if key in _PYRIGHT_PATHS:
        return _absolute_value(value, root, "basedpyright")
    if key == "executionEnvironments":
        return _environments(value, root)
    if isinstance(value, dict):
        return _pyright_paths(cast(dict[str, object], value), root)
    return value


def _environments(value: object, root: Path) -> object:
    if not isinstance(value, list):
        raise LintError("basedpyright executionEnvironments is not a list")
    found: list[object] = []
    for item in cast(list[object], value):
        if not isinstance(item, dict):
            raise LintError("basedpyright execution environment is not a table")
        found.append(_pyright_paths(cast(dict[str, object], item), root))
    return found


def _keep_shadow(config: dict[str, object], shadow: str) -> None:
    raw = config.get("include")
    if not isinstance(raw, list):
        raise LintError("basedpyright include is not a list")
    items: list[str] = []
    for item in cast(list[object], raw):
        if not isinstance(item, str):
            raise LintError("basedpyright include is not a list of strings")
        items.append(item)
    if shadow not in items:
        items.append(shadow)
    config["include"] = items


def _overlay(
    base: dict[str, object],
    override: dict[str, object],
) -> dict[str, object]:
    merged = dict(base)
    for key, value in override.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _overlay(
                cast(dict[str, object], current),
                cast(dict[str, object], value),
            )
            continue
        merged[key] = value
    return merged


def _absolute_paths(data: dict[str, object], root: Path) -> dict[str, object]:
    rewritten: dict[str, object] = {}
    for key, value in data.items():
        if key in _PATH_KEYS:
            rewritten[key] = _absolute_value(value, root, "ruff")
        elif isinstance(value, dict):
            nested = _absolute_paths(cast(dict[str, object], value), root)
            rewritten[key] = nested
        else:
            rewritten[key] = value
    return rewritten


def _absolute_value(value: object, root: Path, checker: str) -> object:
    if isinstance(value, str):
        return _absolute_path(value, root)
    if not isinstance(value, list):
        raise LintError(f"{checker} path setting is not a string")
    rows = cast(list[object], value)
    return [_absolute_item(item, root, checker) for item in rows]


def _absolute_item(value: object, root: Path, checker: str) -> object:
    if not isinstance(value, str):
        raise LintError(f"{checker} path setting is not a string")
    return _absolute_path(value, root)


def _absolute_path(value: str, root: Path) -> str:
    path = Path(value)
    if path.is_absolute():
        return path.as_posix()
    if any(char in value for char in "*?["):
        return (root / path).as_posix()
    return (root / path).resolve().as_posix()


def _resolve_extend(path: Path, extend: str) -> Path:
    target = Path(extend)
    if not target.is_absolute():
        target = path.parent / target
    if not target.is_file():
        raise LintError(f"{path} extends missing {target}")
    return target


def _toml_file(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise LintError(f"cannot read {path}") from err
    try:
        loaded = cast(dict[str, object], tomllib.loads(text))
    except tomllib.TOMLDecodeError as err:
        raise LintError(f"cannot parse {path}") from err
    return loaded


def _json_file(path: Path) -> dict[str, object]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise LintError(f"cannot read {path}") from err
    try:
        loaded = cast(object, json.loads(text))
    except json.JSONDecodeError as err:
        raise LintError(f"cannot parse {path}") from err
    if not isinstance(loaded, dict):
        raise LintError(f"{path} is not a table")
    return cast(dict[str, object], loaded)


def _toml(data: dict[str, object]) -> str:
    lines: list[str] = []
    _emit(lines, (), data)
    return "\n".join(lines).rstrip() + "\n"


def _emit(
    lines: list[str],
    parts: tuple[str, ...],
    data: dict[str, object],
) -> None:
    scalars = [
        (key, value)
        for key, value in data.items()
        if not isinstance(value, dict)
    ]
    tables = [
        (key, cast(dict[str, object], value))
        for key, value in data.items()
        if isinstance(value, dict)
    ]
    if parts and scalars:
        lines.append(f"[{'.'.join(_key(part) for part in parts)}]")
    for key, value in scalars:
        lines.append(f"{_key(key)} = {_literal(value)}")
    if scalars and tables:
        lines.append("")
    for key, value in tables:
        _emit(lines, (*parts, key), value)


def _literal(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, list):
        rows = cast(list[object], value)
        inner = ", ".join(_literal(item) for item in rows)
        return f"[{inner}]"
    if isinstance(value, dict):
        return _inline(cast(dict[str, object], value))
    raise LintError("ruff config has an unsupported value")


def _inline(data: dict[str, object]) -> str:
    parts = [f"{_key(key)} = {_literal(value)}" for key, value in data.items()]
    return "{ " + ", ".join(parts) + " }"


def _key(key: str) -> str:
    if _KEY.fullmatch(key):
        return key
    return _toml_string(key)


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _write(path: Path, text: str) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == text:
        return
    _ = path.write_text(text, encoding="utf-8")
