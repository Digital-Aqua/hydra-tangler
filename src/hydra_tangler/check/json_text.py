""" Slice a JSON value out of checker stdout.

Checkers sometimes print a banner before the payload. This module
does not interpret the payload.
"""

import json
from typing import cast

from hydra_tangler.check.errors import LintError


def json_value(text: str) -> object:
    """ Return the first JSON object or array in ``text``. """
    start = _start(text)
    if start < 0:
        raise LintError("checker output was not JSON")
    try:
        return cast(object, json.loads(text[start:]))
    except json.JSONDecodeError as err:
        raise LintError("checker output was not JSON") from err


def _start(text: str) -> int:
    candidates = [text.find("{"), text.find("[")]
    present = [index for index in candidates if index >= 0]
    if not present:
        return -1
    return min(present)
