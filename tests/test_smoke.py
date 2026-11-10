""" Environment smoke test: the package imports. """

import hydra_tangler


def test_package_imports() -> None:
    assert hydra_tangler is not None
