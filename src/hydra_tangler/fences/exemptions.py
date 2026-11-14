""" Checker rules a tangled fragment is not expected to satisfy.

A fence class lists exclusions. The checker named there turns the
rule codes into its own flags. This module does not run checkers and
does not read configuration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Exclusion:
    """ Rules one checker should drop for a language.

    ``checker`` matches ``Checker.name`` (``ruff``, ``basedpyright``).
    ``rules`` are that checker's own codes, in the order they should
    be applied.
    """

    checker: str
    rules: tuple[str, ...]


def rules_for(
    exclusions: tuple[Exclusion, ...],
    checker: str,
) -> tuple[str, ...]:
    """ Codes ``checker`` should drop, in declaration order.

    A checker named on more than one exclusion contributes every
    code once. Other checkers contribute nothing.
    """
    found: list[str] = []
    for item in exclusions:
        if item.checker != checker:
            continue
        for rule in item.rules:
            if rule not in found:
                found.append(rule)
    return tuple(found)
