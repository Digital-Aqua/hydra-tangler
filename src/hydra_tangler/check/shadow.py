""" Write the python output where checkers can read it.

The tree lives at ``<project>/.hydra/shadow``. A ``.gitignore``
containing ``*`` is written inside that directory so the projection
is not committed. This module does not run checkers.
"""

from pathlib import Path

from hydra_tangler.model import FileSet
from hydra_tangler.writer import write_files

_IGNORE = "*\n"


def prepare_shadow(files: FileSet, directory: Path) -> tuple[Path, ...]:
    """ Write ``files`` and return the Python files in that tree. """
    directory.mkdir(parents=True, exist_ok=True)
    _ensure_ignore(directory / ".gitignore")
    write_files(files, directory)
    return tuple(
        directory / item.path
        for item in files.files
        if item.path.suffix == ".py"
    )


def _ensure_ignore(path: Path) -> None:
    if path.is_file() and path.read_text(encoding="utf-8") == _IGNORE:
        return
    _ = path.write_text(_IGNORE, encoding="utf-8")
