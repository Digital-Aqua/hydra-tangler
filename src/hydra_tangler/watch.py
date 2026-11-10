""" Call a callback when Markdown under a directory changes.

The live source is ``watchfiles``, debounced, limited to ``*.md``.
Tests pass ``batches`` and never sleep. Writes outside the source
directory cannot wake this loop; a target placed under the source
is ignored when the caller names it. This module does not tangle.
"""

from collections.abc import Callable, Iterable, Sequence
from pathlib import Path


def watch_markdown(
    directory: Path,
    on_change: Callable[[], None],
    ignore: Sequence[Path] = (),
    batches: Iterable[Sequence[Path]] | None = None,
) -> None:
    """ Invoke ``on_change`` for each batch that touches Markdown.

    ``batches`` replaces the live watcher. ``ignore`` lists directories
    whose changes must not count, such as a build target inside the
    source tree.
    """
    source = batches if batches is not None else _live(directory)
    ignored = tuple(path.resolve() for path in ignore)
    for batch in source:
        if _relevant(batch, ignored):
            on_change()


def _live(directory: Path) -> Iterable[Sequence[Path]]:
    from watchfiles import watch

    for changes in watch(directory, debounce=300, step=50):
        yield tuple(Path(path) for _kind, path in changes)


def _relevant(batch: Sequence[Path], ignore: Sequence[Path]) -> bool:
    for path in batch:
        if path.suffix != ".md":
            continue
        if _ignored(path, ignore):
            continue
        return True
    return False


def _ignored(path: Path, ignore: Sequence[Path]) -> bool:
    resolved = path.resolve()
    return any(
        resolved == root or _inside(resolved, root) for root in ignore
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        _ = path.relative_to(root)
    except ValueError:
        return False
    return True
