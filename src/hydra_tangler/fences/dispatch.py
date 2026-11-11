""" Choose a fence class for one fence and claim it.

A fence with no ``file`` attribute is ignored, including one that only
sets ``tangler``. This module does not load entry points and does not
write files.
"""

from collections.abc import Mapping

from hydra_tangler.fences.base import Claim
from hydra_tangler.fences.plaintext import PlainText
from hydra_tangler.model import Diagnostic, Fence

_TEST_PREFIX = "test:"


def claim_fence(
    fence: Fence,
    classes: Mapping[str, PlainText],
) -> Claim | None:
    """ Apply the dispatch rules and return a claim, or None to ignore. """
    raw = fence.attrs.get("file")
    if raw is None:
        return None
    if raw.startswith(_TEST_PREFIX):
        return Claim(diagnostic=_test_removed(fence))
    chosen = _choose(fence, classes, raw)
    if isinstance(chosen, Diagnostic):
        return Claim(diagnostic=chosen)
    return chosen.claim(fence)


def _choose(
    fence: Fence,
    classes: Mapping[str, PlainText],
    raw: str,
) -> PlainText | Diagnostic:
    tangler = fence.attrs.get("tangler")
    if tangler is not None:
        found = classes.get(tangler)
        if found is None:
            return _unknown_tangler(fence, tangler, raw)
        return found
    found = classes.get(fence.language)
    if found is None:
        return _unsupported(fence, raw)
    return found


def _unsupported(fence: Fence, raw: str) -> Diagnostic:
    tag = fence.language if fence.language else "(none)"
    return Diagnostic(
        fence.path,
        fence.open_line,
        "warning",
        "unsupported-language",
        (
            f"unsupported language {tag!r} for file {raw}; "
            "use tangler=text"
        ),
    )


def _unknown_tangler(fence: Fence, name: str, raw: str) -> Diagnostic:
    return Diagnostic(
        fence.path,
        fence.open_line,
        "warning",
        "unknown-tangler",
        f"unknown tangler {name!r} for file {raw}",
    )


def _test_removed(fence: Fence) -> Diagnostic:
    return Diagnostic(
        fence.path,
        fence.open_line,
        "error",
        "test-prefix-removed",
        (
            "test: prefix was removed; write the path explicitly, "
            "e.g. file=tests/x.py"
        ),
    )
