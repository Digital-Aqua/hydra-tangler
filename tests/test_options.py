"""Initialization options and analysis failures."""

from pathlib import Path

import pytest

from hydra_tangler.book import UnreadableSource
from hydra_tangler.model import FileSet, OutputFile
from hydra_tangler.outputs.base import Rendered
from hydra_tangler.serve.analysis import decode_tangled_python
from hydra_tangler.serve.options import read_options
from hydra_tangler.sourcemap import SourceMap


def test_checker_commands_are_copied() -> None:
    options = read_options(
        {
            "write": True,
            "pyrightCommand": ["basedpyright-langserver", "--stdio"],
            "ruffCommand": ["ruff", "check"],
        }
    )
    assert options.write is True
    assert options.pyright == ("basedpyright-langserver", "--stdio")
    assert options.ruff == ("ruff", "check")
    assert options.rejected == ()


def test_a_bad_command_is_rejected_and_the_default_kept() -> None:
    options = read_options(
        {
            "pyrightCommand": "",
            "ruffCommand": ["ruff"],
        }
    )
    assert options.pyright == ()
    assert options.ruff == ("ruff",)
    assert options.rejected == (_bad("pyrightCommand"),)


def test_undecodable_python_names_the_file() -> None:
    rendered = Rendered(
        FileSet((OutputFile(Path("pkg/m.py"), b"\xff"),)),
        SourceMap(()),
    )
    with pytest.raises(UnreadableSource, match="pkg/m.py"):
        _ = decode_tangled_python(rendered)


def _bad(name: str) -> str:
    return (
        "bad-checker-command: " + name + " must be a list of non-empty strings"
    )


def test_a_missing_command_keeps_the_default() -> None:
    options = read_options({"write": False})
    assert options.pyright == ()
    assert options.ruff == ()
    assert options.rejected == ()
