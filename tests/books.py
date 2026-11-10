""" Build small Markdown books in a temporary directory.

Helpers for tests. Not part of the tangler.
"""

from pathlib import Path


def fence(info: str, *body: str, ticks: int = 3) -> str:
    """ Return one fenced block, including its trailing newline. """
    bar = "`" * ticks
    return "\n".join((f"{bar}{info}", *body, bar)) + "\n"


def write_chapter(root: Path, relative: str, text: str) -> None:
    """ Write a Markdown file under ``root``. """
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")
