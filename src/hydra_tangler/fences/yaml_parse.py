"""Parse one YAML fence body into an unresolved node tree.

Uses PyYAML's event stream so an alias stays an alias. Dumping a
resolved value lives here too, so the untyped PyYAML import stays in
one module. This module does not merge trees, resolve aliases, or
write files. ``yaml.compose`` and ``safe_load`` are not used: the
composer replaces an alias with the anchored node.
"""

# PyYAML publishes no type information. Keep the gaps in this module.
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAny=false

from dataclasses import dataclass
from pathlib import Path

import yaml
from yaml.constructor import SafeConstructor
from yaml.nodes import ScalarNode as YamlScalar
from yaml.resolver import Resolver

from hydra_tangler.fences.base import Emission
from hydra_tangler.model import Diagnostic

_NO_WRAP = 10**9
_RESOLVER = Resolver()

type Node = ScalarNode | SequenceNode | MappingNode | AliasNode


@dataclass(frozen=True)
class ScalarNode:
    """A scalar whose tag was resolved with the safe constructor.

    Aliases are not scalars. A null scalar is a real value; only the
    merger treats a root null as an empty document.
    """

    value: object


@dataclass(frozen=True)
class SequenceNode:
    """A sequence whose items are still unresolved."""

    items: tuple[Node, ...]


@dataclass(frozen=True)
class MappingNode:
    """A mapping with scalar keys in source order.

    Keys are the resolved scalar values, so ``1`` and ``"1"`` stay
    distinct. The key node itself is not kept.
    """

    pairs: tuple[tuple[object, Node], ...]


@dataclass(frozen=True)
class AliasNode:
    """An alias. The name is not looked up until after the merge."""

    name: str
    path: Path
    line: int


@dataclass(frozen=True)
class Anchor:
    """One anchor name bound to the node it was written on."""

    name: str
    node: Node
    path: Path
    line: int


@dataclass(frozen=True)
class Parsed:
    """One fence reduced to a single unresolved document.

    ``node`` is None when the fence contains no document. A root null
    scalar is still a node here. ``emission`` is the fence that was
    parsed, used when a later merge fails.
    """

    node: Node | None
    anchors: tuple[Anchor, ...]
    emission: Emission


def parse_fence(emission: Emission) -> Parsed | Diagnostic:
    """Parse ``emission`` as one YAML document, or return an error.

    Zero documents is a null document. More than one document, a
    parser error, a non-scalar key, or a repeated anchor in this
    fence is a diagnostic. The file is the caller's to refuse.
    """
    try:
        events = list(yaml.parse("\n".join(emission.lines)))
    except yaml.YAMLError as error:
        return _marked(emission, error)
    return _Tree(emission).consume(events)


def dump_document(value: object, emission: Emission) -> str | Diagnostic:
    """Dump a resolved document in block style, without sorting keys.

    Line wrap is disabled. A representer error is ``yaml-syntax`` on
    ``emission``. This does not invent anchors; the caller must not
    share container identity.
    """
    try:
        rendered = yaml.safe_dump(
            value,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True,
            width=_NO_WRAP,
        )
    except yaml.YAMLError as error:
        return _marked(emission, error)
    return str(rendered)


def markdown_line(emission: Emission, mark_line: int | None) -> int:
    """Map a 0-based body line onto the fence's Markdown line.

    ``mark_line`` comes from a PyYAML mark. An index past the body
    uses the fence's opening line.
    """
    if mark_line is None:
        return emission.open_line
    if 0 <= mark_line < len(emission.markdown_lines):
        return emission.markdown_lines[mark_line]
    return emission.open_line


class _Tree:
    """Fold a PyYAML event stream into one unresolved document.

    ``stack`` holds the sequence or mapping that is still open.
    ``documents`` receives each finished root. ``failure`` stops the
    walk at the first error.
    """

    def __init__(self, emission: Emission) -> None:
        self.emission: Emission = emission
        self.anchors: list[Anchor] = []
        self.documents: list[Node | None] = []
        self.stack: list[_Map | _Seq] = []
        self.root: Node | None = None
        self.seen_root: bool = False
        self.failure: Diagnostic | None = None

    def consume(self, events: list[object]) -> Parsed | Diagnostic:
        """Walk ``events`` and return the document or the first error."""
        for event in events:
            if self.failure is not None:
                break
            self._on(event)
        return self._result()

    def _on(self, event: object) -> None:
        if self._on_document(event):
            return
        self._on_node(event)

    def _on_document(self, event: object) -> bool:
        match event:
            case yaml.StreamStartEvent() | yaml.StreamEndEvent():
                return True
            case yaml.DocumentStartEvent():
                self._start_document(event)
                return True
            case yaml.DocumentEndEvent():
                self._end_document()
                return True
            case _:
                return False

    def _on_node(self, event: object) -> None:
        match event:
            case yaml.ScalarEvent():
                self._scalar(event)
            case yaml.AliasEvent():
                self._alias(event)
            case yaml.SequenceStartEvent():
                self.stack.append(_Seq(event.anchor, _mark_line(event)))
            case yaml.SequenceEndEvent():
                self._end_sequence()
            case yaml.MappingStartEvent():
                self.stack.append(_Map(event.anchor, _mark_line(event)))
            case yaml.MappingEndEvent():
                self._end_mapping()
            case _:
                self._fail(None, "yaml-syntax", "YAML syntax error")

    def _start_document(self, event: object) -> None:
        if self.documents or self.seen_root or self.stack:
            self._fail(
                _mark_line(event),
                "yaml-syntax",
                "YAML fence contains more than one document",
            )
            return
        self.root = None
        self.seen_root = False

    def _end_document(self) -> None:
        if self.stack:
            self._fail(None, "yaml-syntax", "YAML syntax error")
            return
        self.documents.append(self.root)
        self.root = None
        self.seen_root = False

    def _scalar(self, event: yaml.ScalarEvent) -> None:
        try:
            value = _resolved_scalar(event)
        except yaml.YAMLError as error:
            self._fail(_mark_line(event), "yaml-syntax", _problem(error))
            return
        line = _mark_line(event)
        node = ScalarNode(value)
        self._bind(event.anchor, node, line)
        self._place(node, line)

    def _alias(self, event: yaml.AliasEvent) -> None:
        name = event.anchor
        line = _mark_line(event)
        if not isinstance(name, str):
            self._fail(line, "yaml-syntax", "YAML syntax error")
            return
        node = AliasNode(
            name,
            self.emission.markdown_path,
            markdown_line(self.emission, line),
        )
        self._place(node, line)

    def _end_sequence(self) -> None:
        frame = self._take_sequence()
        if frame is None:
            return
        node = SequenceNode(tuple(frame.items))
        self._bind(frame.anchor, node, frame.line)
        self._place(node, frame.line)

    def _end_mapping(self) -> None:
        frame = self._take_mapping()
        if frame is None:
            return
        if frame.has_key:
            self._fail(frame.line, "yaml-syntax", "YAML syntax error")
            return
        node = MappingNode(tuple(frame.pairs))
        self._bind(frame.anchor, node, frame.line)
        self._place(node, frame.line)

    def _take_sequence(self) -> _Seq | None:
        frame = self.stack[-1] if self.stack else None
        if not isinstance(frame, _Seq):
            self._fail(None, "yaml-syntax", "YAML syntax error")
            return None
        _ = self.stack.pop()
        return frame

    def _take_mapping(self) -> _Map | None:
        frame = self.stack[-1] if self.stack else None
        if not isinstance(frame, _Map):
            self._fail(None, "yaml-syntax", "YAML syntax error")
            return None
        _ = self.stack.pop()
        return frame

    def _place(self, node: Node, line: int | None) -> None:
        if self.failure is not None:
            return
        if not self.stack:
            self._place_root(node)
            return
        frame = self.stack[-1]
        if isinstance(frame, _Seq):
            frame.items.append(node)
            return
        self._place_in_mapping(frame, node, line)

    def _place_root(self, node: Node) -> None:
        if self.seen_root:
            self._fail(
                None,
                "yaml-syntax",
                "YAML fence contains more than one document",
            )
            return
        self.root = node
        self.seen_root = True

    def _place_in_mapping(
        self, frame: _Map, node: Node, line: int | None
    ) -> None:
        if frame.has_key:
            frame.pairs.append((frame.key, node))
            frame.has_key = False
            frame.key = None
            return
        if not isinstance(node, ScalarNode):
            self._fail(line, "yaml-syntax", "YAML mapping key must be a scalar")
            return
        frame.key = node.value
        frame.has_key = True

    def _bind(self, name: object, node: Node, line: int | None) -> None:
        if not isinstance(name, str) or self.failure is not None:
            return
        for anchor in self.anchors:
            if anchor.name == name:
                self._fail(
                    line,
                    "yaml-merge",
                    f"duplicate YAML anchor {name!r}",
                )
                return
        self.anchors.append(
            Anchor(
                name,
                node,
                self.emission.markdown_path,
                markdown_line(self.emission, line),
            )
        )

    def _fail(self, line: int | None, code: str, message: str) -> None:
        if self.failure is not None:
            return
        self.failure = Diagnostic(
            self.emission.markdown_path,
            markdown_line(self.emission, line),
            "error",
            code,
            message,
        )

    def _result(self) -> Parsed | Diagnostic:
        if self.failure is not None:
            return self.failure
        if self.stack or self.seen_root:
            return _syntax(self.emission, None, "YAML syntax error")
        if len(self.documents) > 1:
            return _syntax(
                self.emission,
                None,
                "YAML fence contains more than one document",
            )
        if not self.documents:
            return Parsed(None, (), self.emission)
        return Parsed(self.documents[0], tuple(self.anchors), self.emission)


class _Seq:
    """A sequence still receiving items."""

    def __init__(self, anchor: object, line: int | None) -> None:
        self.anchor: object = anchor
        self.line: int | None = line
        self.items: list[Node] = []


class _Map:
    """A mapping still receiving keys and values."""

    def __init__(self, anchor: object, line: int | None) -> None:
        self.anchor: object = anchor
        self.line: int | None = line
        self.pairs: list[tuple[object, Node]] = []
        self.key: object | None = None
        self.has_key: bool = False


def _resolved_scalar(event: yaml.ScalarEvent) -> object:
    tag = event.tag
    if tag is None or tag == "!":
        tag = _RESOLVER.resolve(YamlScalar, event.value, event.implicit)
    node = YamlScalar(
        tag,
        event.value,
        event.start_mark,
        event.end_mark,
        style=event.style,
    )
    return SafeConstructor().construct_object(node, True)


def _marked(emission: Emission, error: yaml.YAMLError) -> Diagnostic:
    return _syntax(emission, _error_line(error), _problem(error))


def _syntax(emission: Emission, line: int | None, message: str) -> Diagnostic:
    return Diagnostic(
        emission.markdown_path,
        markdown_line(emission, line),
        "error",
        "yaml-syntax",
        message,
    )


def _problem(error: yaml.YAMLError) -> str:
    problem = getattr(error, "problem", None)
    if isinstance(problem, str) and problem:
        return f"YAML syntax error: {problem}"
    return "YAML syntax error"


def _error_line(error: yaml.YAMLError) -> int | None:
    return _mark_line_of(getattr(error, "problem_mark", None))


def _mark_line(event: object) -> int | None:
    return _mark_line_of(getattr(event, "start_mark", None))


def _mark_line_of(mark: object) -> int | None:
    line = getattr(mark, "line", None)
    if isinstance(line, int):
        return line
    return None
