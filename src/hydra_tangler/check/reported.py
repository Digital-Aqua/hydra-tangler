""" One checker finding, still pointing at a shadow file.

Mapping onto Markdown is a later step. This module does not run
checkers or read the source map.
"""

from dataclasses import dataclass

from hydra_tangler.model import Severity


@dataclass(frozen=True)
class Reported:
    """ A finding as the checker printed it.

    ``file`` is the path string from the tool. ``line`` is 1-based.
    """

    file: str
    line: int
    severity: Severity
    code: str
    message: str
