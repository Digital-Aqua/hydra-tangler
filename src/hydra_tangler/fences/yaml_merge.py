"""Deep-merge YAML fences that share an output path.

Anchor tables are united before aliases are resolved, and the merge
does not follow aliases. A single fence is copied through unchanged.
This module does not concatenate other languages and does not write
files. PyYAML stays in the parse module.
"""

import copy
from collections.abc import Sequence

from hydra_tangler.fences.base import Emission, JoinResult, LocatedLine
from hydra_tangler.fences.plaintext import concatenate
from hydra_tangler.fences.yaml_parse import (
    AliasNode,
    Anchor,
    MappingNode,
    Node,
    Parsed,
    ScalarNode,
    SequenceNode,
    dump_document,
    parse_fence,
)
from hydra_tangler.model import Diagnostic


class _YamlMerge:
    """Deep-merge two or more YAML emissions.

    One emission uses the concatenate joiner, so anchors in a single
    fence stay in the source text.
    """

    name: str = "yaml"

    def join(self, emissions: Sequence[Emission]) -> JoinResult:
        """Return the merged body, or one error and no lines."""
        if len(emissions) < 2:
            return concatenate.join(emissions)
        try:
            lines = _merged_lines(emissions)
        except _Failed as failed:
            return JoinResult(diagnostic=failed.diagnostic)
        return JoinResult(lines=lines)


class _Failed(Exception):
    """A merge problem, carried as a diagnostic.

    It does not leave ``join``. Callers see a ``JoinResult``.
    """

    def __init__(self, diagnostic: Diagnostic) -> None:
        self.diagnostic: Diagnostic = diagnostic
        super().__init__(diagnostic.message)


yaml_joiner = _YamlMerge()


def _merged_lines(emissions: Sequence[Emission]) -> tuple[LocatedLine, ...]:
    parsed = tuple(_require(parse_fence(emission)) for emission in emissions)
    table = _union(parsed)
    merged = _fold_roots(parsed, table)
    if merged is None:
        return ()
    value = _resolve(merged, table, ())
    text = _dumped(value, emissions[0])
    origin = emissions[0]
    return tuple(
        LocatedLine(line, origin.markdown_path, origin.open_line)
        for line in text.splitlines()
    )


def _require(parsed: Parsed | Diagnostic) -> Parsed:
    if isinstance(parsed, Diagnostic):
        raise _Failed(parsed)
    return parsed


def _dumped(value: object, emission: Emission) -> str:
    text = dump_document(value, emission)
    if isinstance(text, Diagnostic):
        raise _Failed(text)
    return text


def _union(parsed: Sequence[Parsed]) -> dict[str, Node]:
    table: dict[str, Node] = {}
    seen: dict[str, Anchor] = {}
    for item in parsed:
        for anchor in item.anchors:
            _keep_anchor(table, seen, anchor)
    return table


def _keep_anchor(
    table: dict[str, Node],
    seen: dict[str, Anchor],
    anchor: Anchor,
) -> None:
    if anchor.name in seen:
        raise _Failed(
            Diagnostic(
                anchor.path,
                anchor.line,
                "error",
                "yaml-merge",
                f"duplicate YAML anchor {anchor.name!r}",
            )
        )
    seen[anchor.name] = anchor
    table[anchor.name] = anchor.node


def _fold_roots(
    parsed: Sequence[Parsed],
    table: dict[str, Node],
) -> Node | None:
    """Merge document roots. A missing root or a root null adds nothing.

    A nested null is a scalar. ``_combine`` handles that, not this
    function.
    """
    merged: Node | None = None
    for item in parsed:
        merged = _merge_root(merged, item.node, table, item)
    return merged


def _merge_root(
    merged: Node | None,
    node: Node | None,
    table: dict[str, Node],
    item: Parsed,
) -> Node | None:
    if node is None or _root_null(node):
        return merged
    if merged is None:
        return node
    return _combine(merged, node, table, item)


def _root_null(node: Node) -> bool:
    return isinstance(node, ScalarNode) and node.value is None


def _combine(
    left: Node,
    right: Node,
    table: dict[str, Node],
    item: Parsed,
) -> Node:
    if isinstance(left, AliasNode) or isinstance(right, AliasNode):
        return right
    if isinstance(left, ScalarNode) and isinstance(right, ScalarNode):
        return right
    if isinstance(left, MappingNode) and isinstance(right, MappingNode):
        return _combine_maps(left, right, table, item)
    if isinstance(left, SequenceNode) and isinstance(right, SequenceNode):
        return _combine_sequences(left, right, table)
    raise _Failed(_clash(item, left, right))


def _combine_maps(
    left: MappingNode,
    right: MappingNode,
    table: dict[str, Node],
    item: Parsed,
) -> MappingNode:
    pairs = list(left.pairs)
    for key, value in right.pairs:
        index = _find(pairs, key)
        if index is None:
            pairs.append((key, value))
            continue
        merged = _combine(pairs[index][1], value, table, item)
        pairs[index] = (pairs[index][0], merged)
    combined = MappingNode(tuple(pairs))
    _retarget(table, left, right, combined)
    return combined


def _combine_sequences(
    left: SequenceNode,
    right: SequenceNode,
    table: dict[str, Node],
) -> SequenceNode:
    combined = SequenceNode(left.items + right.items)
    _retarget(table, left, right, combined)
    return combined


def _find(pairs: Sequence[tuple[object, Node]], key: object) -> int | None:
    for index, (found, _) in enumerate(pairs):
        if found == key:
            return index
    return None


def _retarget(
    table: dict[str, Node],
    left: Node,
    right: Node,
    combined: Node,
) -> None:
    # A later alias must see the merged node, not the side the anchor
    # was first attached to. Replacing a node does not call this.
    for name, node in tuple(table.items()):
        if node is left or node is right:
            table[name] = combined


def _clash(item: Parsed, left: Node, right: Node) -> Diagnostic:
    return Diagnostic(
        item.emission.markdown_path,
        item.emission.open_line,
        "error",
        "yaml-merge",
        f"cannot merge YAML {_kind(left)} with {_kind(right)}",
    )


def _kind(node: Node) -> str:
    if isinstance(node, MappingNode):
        return "mapping"
    if isinstance(node, SequenceNode):
        return "sequence"
    if isinstance(node, ScalarNode):
        return "scalar"
    return "alias"


def _resolve(
    node: Node,
    table: dict[str, Node],
    stack: tuple[str, ...],
) -> object:
    if isinstance(node, AliasNode):
        return _alias_value(node, table, stack)
    if isinstance(node, ScalarNode):
        return node.value
    if isinstance(node, SequenceNode):
        return [_resolve(item, table, stack) for item in node.items]
    return _mapping(node, table, stack)


def _alias_value(
    node: AliasNode,
    table: dict[str, Node],
    stack: tuple[str, ...],
) -> object:
    if node.name in stack:
        message = f"YAML alias {node.name!r} is cyclic"
        raise _Failed(_alias_diagnostic(node, message))
    target = table.get(node.name)
    if target is None:
        message = f"unknown YAML alias {node.name!r}"
        raise _Failed(_alias_diagnostic(node, message))
    resolved = _resolve(target, table, stack + (node.name,))
    return copy.deepcopy(resolved)


def _alias_diagnostic(node: AliasNode, message: str) -> Diagnostic:
    return Diagnostic(node.path, node.line, "error", "yaml-syntax", message)


def _mapping(
    node: MappingNode,
    table: dict[str, Node],
    stack: tuple[str, ...],
) -> dict[object, object]:
    built: dict[object, object] = {}
    for key, value in node.pairs:
        built[key] = _resolve(value, table, stack)
    return built
