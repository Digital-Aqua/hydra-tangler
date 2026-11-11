""" The failures a user should see as a message, not a traceback.

Problems in a book are diagnostics and never appear here. Everything
in ``USER_FAILURES`` is a missing tool, bad tool output, an unreadable
file, a refused write, or a broken programmer invariant. The command
line prints each as ``error: ...`` and exits 1. The language server
shows each as a message and keeps running. This module does not catch
or print anything itself.
"""

from hydra_tangler.book import SourceMissing, UnreadableSource
from hydra_tangler.check.errors import LintError
from hydra_tangler.fences import FenceLoadError
from hydra_tangler.model import UnsafeOutputPath
from hydra_tangler.outputs import OutputLoadError, UnknownOutput
from hydra_tangler.outputs.htmldocs.headings import HeadingSlugMismatch
from hydra_tangler.outputs.htmldocs.render import FenceMismatch
from hydra_tangler.writer import WriterError

USER_FAILURES = (
    SourceMissing,
    UnreadableSource,
    WriterError,
    UnknownOutput,
    FenceLoadError,
    OutputLoadError,
    LintError,
    UnsafeOutputPath,
    OSError,
    UnicodeDecodeError,
    HeadingSlugMismatch,
    FenceMismatch,
)
