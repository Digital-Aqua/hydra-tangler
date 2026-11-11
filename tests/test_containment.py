""" Output paths stay inside the target directory.

Fences, ``OutputFile``, mounts, and the writer share one path rule.
These tests cover escapes, malformed paths, symlink refusal, and a
tampered manifest. They do not check source maps or HTML output.
"""

import json
from pathlib import Path

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.fences.plaintext import PlainText
from hydra_tangler.model import (
    Book,
    Document,
    Fence,
    FileSet,
    OutputFile,
    RejectedPath,
    UnsafeOutputPath,
    vet_output_path,
)
from hydra_tangler.mounting import require_mount
from hydra_tangler.outputs import OutputLoadError, check_mount
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.outputs.files import FilesOutput
from hydra_tangler.pipeline import render_outputs
from hydra_tangler.sourcemap import SourceMap
from hydra_tangler.writer import WriterError, write_files

_ESCAPES = (
    "../x",
    "a/../../x",
    "./../x",
    "/abs",
    "a\\..\\x",
)
_MALFORMED = (
    "",
    "a\x00b",
    "<test:api/x.py>",
    "a:b.py",
    "what?.py",
    "a*b",
    'q"x',
    "a|b",
    "tab\there",
)


def test_fence_rejects_escapes_and_malformed_paths() -> None:
    handler = PlainText()
    for raw in _ESCAPES:
        claim = handler.claim(_fence(raw))
        assert claim.diagnostic is not None
        assert claim.emission is None
        assert claim.diagnostic.code == "path-escapes-target"
        assert claim.diagnostic.severity == "error"
        assert claim.diagnostic.line == 1
    for raw in _MALFORMED:
        claim = handler.claim(_fence(raw))
        assert claim.diagnostic is not None
        assert claim.diagnostic.code == "bad-path"
        assert claim.diagnostic.severity == "error"


def test_output_file_rejects_the_same_paths() -> None:
    for raw in (*_ESCAPES, *_MALFORMED):
        verdict = vet_output_path(raw)
        assert isinstance(verdict, RejectedPath)
        with pytest.raises(UnsafeOutputPath) as caught:
            _ = OutputFile(Path(raw), b"no")
        assert caught.value.raw in (raw, Path(raw).as_posix())


def test_parent_segment_inside_the_target_is_kept() -> None:
    item = OutputFile(Path("a/../b"), b"yes")
    assert item.path == Path("b")
    claim = PlainText().claim(_fence("a/../b"))
    assert claim.emission is not None
    assert claim.emission.path == Path("b")
    assert claim.diagnostic is None


def test_normalized_path_is_written(tmp_path: Path) -> None:
    write_chapter(tmp_path, "c.md", fence("python file=a/../b.py", "x = 1"))
    rendered = FilesOutput().render(load_book(tmp_path))
    assert rendered.diagnostics == ()
    assert rendered.files.data_for(Path("b.py")) is not None


def test_escaping_mount_is_a_load_error() -> None:
    require_mount(Path("."))
    require_mount(Path("docs"))
    for raw in _ESCAPES:
        with pytest.raises(UnsafeOutputPath):
            require_mount(Path(raw))
        with pytest.raises(OutputLoadError, match="escapes"):
            check_mount(Path(raw))


def test_symlink_directory_is_not_written(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    target = tmp_path / "build"
    target.mkdir()
    (target / "linked").symlink_to(outside, target_is_directory=True)
    files = FileSet((OutputFile(Path("linked/a.txt"), b"hi"),))
    with pytest.raises(WriterError):
        write_files(files, target)
    assert not (outside / "a.txt").exists()


def test_symlink_directory_is_not_used_for_stale_deletion(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "old.txt"
    _ = sentinel.write_text("keep", encoding="utf-8")
    target = tmp_path / "build"
    target.mkdir()
    (target / "linked").symlink_to(outside, target_is_directory=True)
    _manifest(target, ["linked/old.txt"])
    with pytest.raises(WriterError):
        write_files(FileSet(), target)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_tampered_manifest_cannot_delete_outside(tmp_path: Path) -> None:
    sentinel = tmp_path / "secret"
    _ = sentinel.write_text("keep", encoding="utf-8")
    target = tmp_path / "build"
    target.mkdir()
    _manifest(target, ["../secret"])
    with pytest.raises(WriterError):
        write_files(FileSet(), target)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_one_document_escape_is_a_diagnostic() -> None:
    book = Book(Path("."), (Document(Path("c.md"), (), (), ()),))
    rendered = render_outputs(book, (_Escaping(),))
    problem = rendered[0].rendered.diagnostics[0]
    assert problem.code == "path-escapes-target"
    assert problem.severity == "error"
    assert problem.path == Path("c.md")
    assert "../x" in problem.message


def test_escape_without_one_document_propagates() -> None:
    book = Book(
        Path("."),
        (
            Document(Path("a.md"), (), (), ()),
            Document(Path("b.md"), (), (), ()),
        ),
    )
    with pytest.raises(UnsafeOutputPath, match="../x"):
        _ = render_outputs(book, (_Escaping(),))


class _Escaping:
    """ An output that tries to build a path outside the target. """

    name: str = "escaping"
    mount: Path = Path(".")

    def render(self, book: Book) -> Rendered:
        _ = book
        _ = OutputFile(Path("../x"), b"no")
        return Rendered(FileSet(), SourceMap())


def _fence(raw: str) -> Fence:
    return Fence(
        Path("c.md"),
        "python",
        "python",
        {"file": raw},
        ("x = 1",),
        1,
        2,
    )


def _manifest(target: Path, names: list[str]) -> None:
    payload = json.dumps({"files": names})
    _ = (target / ".hydra-manifest.json").write_text(payload, encoding="utf-8")
