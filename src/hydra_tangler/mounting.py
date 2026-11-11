""" Mount outputs into one target-relative file set.

Each output names a ``mount`` and stays unaware of the others. This
module prefixes file and source-map paths, refuses two claims on one
path, and reserves ``sourcemap.json``. A mount other than ``.`` must
pass the same path rule as an output file. It does not write the
directory.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hydra_tangler.model import (
    Diagnostic,
    FileSet,
    OutputFile,
    RejectedPath,
    UnsafeOutputPath,
    vet_output_path,
)
from hydra_tangler.outputs.base import RenderedOutput
from hydra_tangler.sourcemap import (
    MarkdownSite,
    OutputSite,
    SourceMap,
    SourceRecord,
    to_json,
)

SOURCEMAP_PATH = Path("sourcemap.json")
_CODE = "output-collision"


@dataclass(frozen=True)
class _Claim:
    """ One output file after its mount is applied. """

    name: str
    site: MarkdownSite | None


def require_mount(mount: Path) -> None:
    """ Raise when ``mount`` leaves the target.

    ``.`` is the identity mount and is allowed. Any other mount is
    judged by ``vet_output_path``. The loader turns this into a load
    error. This does not write files.
    """
    if mount == Path("."):
        return
    verdict = vet_output_path(mount.as_posix())
    if isinstance(verdict, RejectedPath):
        raise UnsafeOutputPath(mount.as_posix())


def mount_relative(mount: Path, relative: Path) -> Path:
    """ Prefix ``relative`` with an output mount. ``.`` changes nothing. """
    if mount == Path("."):
        return relative
    return mount / relative


def collision_diagnostics(
    rendered: Sequence[RenderedOutput],
) -> tuple[Diagnostic, ...]:
    """ Errors for a shared mounted path or the reserved map name.

    The diagnostic sits on the Markdown line that produced the file
    when that line is in the output's source map.
    """
    grouped = _claims(rendered)
    found: list[Diagnostic] = []
    for path in sorted(grouped):
        claims = grouped[path]
        if not _collides(path, claims, rendered):
            continue
        found.extend(_diagnostics(path, claims, rendered))
    return tuple(found)


def merged_source_map(rendered: Sequence[RenderedOutput]) -> SourceMap:
    """ Source-map records with target-relative, mounted paths. """
    records: list[SourceRecord] = []
    for item in rendered:
        records.extend(_mounted_records(item))
    return SourceMap(tuple(records))


def assemble_output(
    rendered: Sequence[RenderedOutput],
    *,
    sourcemap: bool,
) -> FileSet:
    """ One file set of mounted paths, plus ``sourcemap.json`` when asked. """
    files = [
        OutputFile(mount_relative(item.mount, output.path), output.data)
        for item in rendered
        for output in item.rendered.files.files
    ]
    if sourcemap:
        text = to_json(merged_source_map(rendered))
        files.append(OutputFile(SOURCEMAP_PATH, text.encode("utf-8")))
    return FileSet(tuple(files))


def _mounted_records(item: RenderedOutput) -> tuple[SourceRecord, ...]:
    return tuple(
        SourceRecord(
            OutputSite(
                mount_relative(item.mount, record.output.path),
                record.output.line,
            ),
            record.markdown,
        )
        for record in item.rendered.source_map.records
    )


def _claims(rendered: Sequence[RenderedOutput]) -> dict[str, list[_Claim]]:
    grouped: dict[str, list[_Claim]] = {}
    for item in rendered:
        for output in item.rendered.files.files:
            mounted = mount_relative(item.mount, output.path)
            key = mounted.as_posix()
            site = _first_site(item.rendered.source_map, output.path)
            grouped.setdefault(key, []).append(_Claim(item.name, site))
    return grouped


def _first_site(source_map: SourceMap, path: Path) -> MarkdownSite | None:
    for record in source_map.records:
        if record.output.path == path:
            return record.markdown
    return None


def _collides(
    path: str,
    claims: Sequence[_Claim],
    rendered: Sequence[RenderedOutput],
) -> bool:
    if path == SOURCEMAP_PATH.as_posix() or len(claims) > 1:
        return True
    owner = _mount_owner(path, rendered)
    if owner is None:
        return False
    return any(claim.name != owner for claim in claims)


def _mount_owner(path: str, rendered: Sequence[RenderedOutput]) -> str | None:
    """ The output whose mount contains ``path``, ignoring mount ``.``. """
    candidate = Path(path)
    for item in rendered:
        if item.mount == Path("."):
            continue
        if candidate == item.mount or _within(candidate, item.mount):
            return item.name
    return None


def _within(path: Path, root: Path) -> bool:
    try:
        _ = path.relative_to(root)
    except ValueError:
        return False
    return True


def _diagnostics(
    path: str,
    claims: Sequence[_Claim],
    rendered: Sequence[RenderedOutput],
) -> tuple[Diagnostic, ...]:
    message = _message(path, claims, rendered)
    sites: list[MarkdownSite] = []
    for claim in claims:
        if claim.site is not None and claim.site not in sites:
            sites.append(claim.site)
    if not sites:
        return (Diagnostic(Path(path), 1, "error", _CODE, message),)
    return tuple(
        Diagnostic(site.path, site.line, "error", _CODE, message)
        for site in sites
    )


def _message(
    path: str,
    claims: Sequence[_Claim],
    rendered: Sequence[RenderedOutput],
) -> str:
    names = ", ".join(claim.name for claim in claims)
    if path == SOURCEMAP_PATH.as_posix():
        return f"{path} is reserved for the combined source map ({names})"
    owner = _mount_owner(path, rendered)
    foreign = owner is not None and any(claim.name != owner for claim in claims)
    if foreign:
        return f"{path} is inside the {owner} mount"
    return f"{path} is claimed by {names}"
