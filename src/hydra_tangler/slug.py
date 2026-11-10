""" Heading slugs shared by link checking and HTML docs.

The rules follow GitHub's heading anchors: lowercase, drop
punctuation, turn spaces into hyphens, and number repeats. This
module does not parse Markdown.
"""

import re

_PUNCTUATION = re.compile(r"[^\w\s-]", re.UNICODE)
_SPACE = re.compile(r"[\s_]+")
_HYPHENS = re.compile(r"-{2,}")


def slugify(text: str) -> str:
    """ Return the base slug for a heading's visible text. """
    lowered = text.strip().lower()
    cleaned = _PUNCTUATION.sub("", lowered)
    hyphenated = _SPACE.sub("-", cleaned)
    return _HYPHENS.sub("-", hyphenated).strip("-")


def unique_slug(text: str, seen: dict[str, int]) -> str:
    """ Return ``slugify(text)``, appending ``-1``, ``-2`` on repeats.

    ``seen`` counts how many times each base slug has been issued in
    the current document. The caller owns that dictionary.
    """
    base = slugify(text)
    count = seen.get(base, 0)
    seen[base] = count + 1
    if count == 0:
        return base
    return f"{base}-{count}"
