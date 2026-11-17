"""Book checker defaults layered under the book's own config."""

import json
from pathlib import Path
from typing import cast

import pytest
from tests.books import fence, write_chapter

from hydra_tangler.book import load_book
from hydra_tangler.check.defaults import basedpyright_config, ruff_config_args
from hydra_tangler.check.errors import LintError
from hydra_tangler.check.lint import lint_python
from hydra_tangler.check.ruff import Ruff
from hydra_tangler.check.tool import CheckerCommands
from hydra_tangler.outputs.files import FilesOutput


def test_ruff_defaults_ignore_sorting_and_unused_noqa(tmp_path: Path) -> None:
    _ = ruff_config_args(tmp_path)
    text = (tmp_path / ".hydra" / "ruff" / "defaults.toml").read_text()
    assert text == '[lint]\nignore = ["I001", "RUF100"]\n'


def test_ruff_toml_beats_pyproject(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff]\nline-length = 100\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "ruff.toml").write_text(
        "line-length = 88\n",
        encoding="utf-8",
    )
    _ = (tmp_path / ".ruff.toml").write_text(
        "line-length = 60\n",
        encoding="utf-8",
    )
    config = Path(ruff_config_args(tmp_path)[-1])
    text = config.read_text(encoding="utf-8")
    assert "line-length = 60" in text
    assert "line-length = 88" not in text
    assert 'ignore = ["I001", "RUF100"]' not in text
    assert "defaults.toml" in text


def test_extend_select_turns_one_ruff_rule_back_on(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.ruff]\nline-length = 100\n\n'
        + '[tool.ruff.lint]\nextend-select = ["I001"]\n'
        + 'ignore = ["E501"]\n',
        encoding="utf-8",
    )
    config = Path(ruff_config_args(tmp_path)[-1])
    text = config.read_text(encoding="utf-8")
    assert 'extend-select = ["I001"]' in text
    assert 'ignore = ["E501"]' in text
    assert "line-length = 100" in text
    parent = text.split("extend = ", 1)[1].split("\n", 1)[0].strip('"')
    assert Path(parent).read_text(encoding="utf-8") == (
        '[lint]\nignore = ["I001", "RUF100"]\n'
    )


def test_ruff_extend_chain_keeps_the_parent_settings(tmp_path: Path) -> None:
    shared = tmp_path / "shared.toml"
    _ = shared.write_text(
        'src = ["src"]\n\n[lint]\nignore = ["E501"]\n',
        encoding="utf-8",
    )
    _ = (tmp_path / "ruff.toml").write_text(
        f'extend = "{shared}"\n\n[lint]\nextend-select = ["RUF100"]\n',
        encoding="utf-8",
    )
    config = Path(ruff_config_args(tmp_path)[-1])
    nearest = config.read_text(encoding="utf-8")
    assert 'extend-select = ["RUF100"]' in nearest
    parent = Path(nearest.split('extend = "', 1)[1].split('"', 1)[0])
    shared_text = parent.read_text(encoding="utf-8")
    assert 'ignore = ["E501"]' in shared_text
    assert str((tmp_path / "src").resolve()) in shared_text
    base = Path(shared_text.split('extend = "', 1)[1].split('"', 1)[0])
    assert "I001" in base.read_text(encoding="utf-8")


def test_a_broken_ruff_config_is_an_error(tmp_path: Path) -> None:
    _ = (tmp_path / "ruff.toml").write_text(
        "line-length = [\n",
        encoding="utf-8",
    )
    with pytest.raises(LintError, match="cannot parse"):
        _ = ruff_config_args(tmp_path)


def test_basedpyright_book_overrides_one_rule(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.basedpyright]\n"
        + 'reportUnnecessaryTypeIgnoreComment = "warning"\n'
        + 'include = ["src"]\n'
        + "reportExplicitAny = false\n",
        encoding="utf-8",
    )
    path = basedpyright_config(tmp_path)
    payload = cast(
        dict[str, object],
        json.loads(path.read_text(encoding="utf-8")),
    )
    shadow = str((tmp_path / ".hydra" / "shadow").resolve())
    assert payload["reportUnnecessaryTypeIgnoreComment"] == "warning"
    assert payload["reportExplicitAny"] is False
    assert payload["typeCheckingMode"] == "recommended"
    assert payload["include"] == [str((tmp_path / "src").resolve()), shadow]


def test_pyrightconfig_beats_pyproject(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.basedpyright]\ntypeCheckingMode = \"all\"\n",
        encoding="utf-8",
    )
    _ = (tmp_path / "pyrightconfig.json").write_text(
        '{"typeCheckingMode": "basic"}\n',
        encoding="utf-8",
    )
    payload = cast(
        dict[str, object],
        json.loads(basedpyright_config(tmp_path).read_text(encoding="utf-8")),
    )
    assert payload["typeCheckingMode"] == "basic"
    assert payload["reportUnnecessaryTypeIgnoreComment"] == "none"


def test_both_pyright_tables_are_an_error(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        '[tool.basedpyright]\ntypeCheckingMode = "recommended"\n\n'
        + '[tool.pyright]\ntypeCheckingMode = "basic"\n',
        encoding="utf-8",
    )
    with pytest.raises(LintError, match="both basedpyright and pyright"):
        _ = basedpyright_config(tmp_path)


def test_extend_select_overrides_one_default(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.ruff.lint]\nextend-select = [\"RUF\"]\n",
        encoding="utf-8",
    )
    rendered = _rendered(
        tmp_path,
        "import sys",
        "import os",
        "name = 1  # noqa: F841",
        "missing",
    )
    project = Path(__file__).resolve().parents[1]
    found = lint_python(
        tmp_path,
        rendered,
        CheckerCommands(
            ruff=(
                "uv",
                "run",
                "--project",
                str(project),
                "ruff",
                "check",
                "--output-format",
                "json",
            )
        ),
        shadow=tmp_path / "shadow",
        checkers=(Ruff(),),
    )
    codes = {item.code for item in found}
    assert "ruff:RUF100" in codes
    assert "ruff:I001" not in codes
    assert "ruff:F821" in codes


def _rendered(root: Path, *body: str):
    write_chapter(root, "c.md", fence("python file=m.py", *body))
    return FilesOutput().render(load_book(root))
