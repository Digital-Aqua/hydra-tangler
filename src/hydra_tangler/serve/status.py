""" Status the language server reports to its client.

``hydra/status`` is a notification. ``hydra/rebuild`` is a request
that returns the same payload once the forced rebuild has finished.
This module does not publish diagnostics or rebuild a book.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from hydra_tangler.model import Diagnostic

HYDRA_STATUS = "hydra/status"
HYDRA_REBUILD = "hydra/rebuild"

ServeState = Literal["busy", "idle"]


@dataclass(frozen=True)
class StatusReport:
    """ How many diagnostics the latest published build produced.

    ``state`` is ``busy`` while a rebuild is waiting to publish and
    ``idle`` after the newest rebuild has published. Counts stay at
    the previous build until that publish.
    """

    state: ServeState
    errors: int
    warnings: int


def status_for(diagnostics: Sequence[Diagnostic]) -> StatusReport:
    """ Count an idle report from diagnostics that were just published. """
    errors = 0
    warnings = 0
    for item in diagnostics:
        if item.severity == "error":
            errors += 1
        else:
            warnings += 1
    return StatusReport("idle", errors, warnings)


def status_payload(report: StatusReport) -> dict[str, str | int]:
    """ The JSON object a client reads for status and rebuild. """
    return {
        "state": report.state,
        "errors": report.errors,
        "warnings": report.warnings,
    }
