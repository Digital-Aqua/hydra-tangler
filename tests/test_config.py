""" ``[tool.hydra.check]`` commands. """

from pathlib import Path

import pytest

from hydra_tangler.config import ConfigError, load_config


def test_check_commands_are_read(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "\n".join(
            (
                "[tool.hydra.check]",
                'pyright = ["basedpyright", "--outputjson"]',
                'ruff = ["ruff", "check"]',
                "",
            )
        ),
        encoding="utf-8",
    )
    config = load_config(tmp_path)
    assert config.check.pyright == ("basedpyright", "--outputjson")
    assert config.check.ruff == ("ruff", "check")


def test_a_bad_check_command_is_rejected(tmp_path: Path) -> None:
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.hydra.check]\npyright = \"basedpyright\"\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="pyright"):
        _ = load_config(tmp_path)
