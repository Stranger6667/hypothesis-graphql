from __future__ import annotations

import string
import zlib
from typing import TYPE_CHECKING, TypeVar, cast

import graphql
from graphql import is_equal_type
from hypothesis import strategies as st

from .._compat import ast_sequence
from .ast import make_document_node
from .oracle import unwrap
from .strategy import make_type_name

if TYPE_CHECKING:
    from hypothesis.internal.conjecture.data import ConjectureData

T = TypeVar("T")
# (field_name, on_type, children, arguments)
SelectionNode = tuple[str, str | None, "list[SelectionNode]", list[graphql.ArgumentNode]]

# Share of documents with any optional syntax; the rest stay plain
SYNTAX = 0.5
# Every field and inline fragment has a site: the checksum of its path modulo `SITES`, which stays the same
# when other selections shrink away. Aliases, directives and named fragments each get `SLOTS` integer draws
# that pick a site and a value, or nothing (zero, the shrink target): about `SLOTS` in `SITES` fields get
# each kind, with a fixed number of draws per document
SITES = 8
SLOTS = 2
DIRECTIVES = [(name, value) for name in ("skip", "include") for value in (False, True)]
_HEAD = string.ascii_letters + "_"
# Every name of one or two characters, except the reserved `__`
NAMES = [*_HEAD, *(head + tail for head in _HEAD for tail in _HEAD + string.digits if head + tail != "__")]


def _slots(data: ConjectureData, values: list[T]) -> dict[int, T]:
    found = {}
    for _ in range(SLOTS):
        index = data.draw_integer(0, SITES * len(values)) - 1
        if index >= 0:
            found[index % SITES] = values[index // SITES]
    return found


class _Syntax:
    """The optional syntax of one document."""

    def __init__(self, data: ConjectureData) -> None:
        self.aliases = _slots(data, NAMES)
        self.directives = _slots(data, DIRECTIVES)
        self.hoists = _slots(data, NAMES)
        # The lower half of the range, with the shrink target, is an anonymous operation
        index = data.draw_integer(0, 2 * len(NAMES) - 1) - len(NAMES)
        self.operation = graphql.NameNode(value=NAMES[index]) if index >= 0 else None
        self.definitions: list[graphql.FragmentDefinitionNode] = []
        # Fields under different fragments merge when their response keys match, at any depth,
        # hence an alias differs from every response key of the document
        self.keys: set[str] = set()
        # `on` is the only name a fragment can not have
        self.fragment_names = {"on"}

    def alias(self, site: int) -> graphql.NameNode | None:
        name = self.aliases.get(site)
        return graphql.NameNode(value=_unique(name, self.keys)) if name is not None else None

    def directive(self, site: int) -> tuple[graphql.DirectiveNode, ...]:
        directive = self.directives.get(site)
        if directive is None:
            return ast_sequence()
        name, value = directive
        argument = graphql.ArgumentNode(name=graphql.NameNode(value="if"), value=graphql.BooleanValueNode(value=value))
        return ast_sequence(
            [graphql.DirectiveNode(name=graphql.NameNode(value=name), arguments=ast_sequence([argument]))]
        )

    def hoist(
        self,
        site: int,
        on_type: str,
        selection_set: graphql.SelectionSetNode,
        directives: tuple[graphql.DirectiveNode, ...],
    ) -> graphql.FragmentSpreadNode | None:
        name = self.hoists.get(site)
        if name is None:
            return None
        name = _unique(name, self.fragment_names)
        self.definitions.append(
            graphql.FragmentDefinitionNode(
                name=graphql.NameNode(value=name),
                type_condition=_named_type(on_type),
                directives=ast_sequence(),
                selection_set=selection_set,
            )
        )
        return graphql.FragmentSpreadNode(name=graphql.NameNode(value=name), directives=directives)


def _conflict_alias(name: str, type_: graphql.GraphQLType) -> str:
    return f"{name}_{make_type_name(type_)}"


def _response_keys(nodes: list[SelectionNode], type_map: dict[str, graphql.GraphQLNamedType], keys: set[str]) -> None:
    for name, on, children, _ in nodes:
        keys.add(name)
        if on is not None:
            keys.add(_conflict_alias(name, _fields(type_map, on)[name].type))
        if children:
            _response_keys(children, type_map, keys)


def _unique(name: str, taken: set[str]) -> str:
    while name in taken:
        name += "_"
    taken.add(name)
    return name


def _fields(type_map: dict[str, graphql.GraphQLNamedType], name: str) -> dict[str, graphql.GraphQLField]:
    fields: dict[str, graphql.GraphQLField] = cast(
        "graphql.GraphQLObjectType | graphql.GraphQLInterfaceType", type_map[name]
    ).fields
    return fields


def _named_type(name: str) -> graphql.NamedTypeNode:
    return graphql.NamedTypeNode(name=graphql.NameNode(value=name))


def _field(
    node: SelectionNode,
    type_map: dict[str, graphql.GraphQLNamedType] | None,
    syntax: _Syntax | None,
    parent: str,
    path: int,
    alias: graphql.NameNode | None = None,
) -> graphql.FieldNode:
    name, on, children, args = node
    directives: tuple[graphql.DirectiveNode, ...] = ast_sequence()
    selection_set = None
    if syntax is None:
        if children:
            selection_set = _build(children, type_map, None, "", 0)
    else:
        path = zlib.crc32(name.encode(), path)
        site = path % SITES
        alias = syntax.alias(site) or alias
        directives = syntax.directive(site)
        if children:
            assert type_map is not None
            target = unwrap(_fields(type_map, on or parent)[name].type).name
            selection_set = _build(children, type_map, syntax, target, path)
            spread = syntax.hoist(site, target, selection_set, ast_sequence())
            if spread is not None:
                selection_set = graphql.SelectionSetNode(selections=ast_sequence([spread]))
    return graphql.FieldNode(
        name=graphql.NameNode(value=name),
        alias=alias,
        arguments=ast_sequence(args),
        directives=directives,
        selection_set=selection_set,
    )


def _build(
    nodes: list[SelectionNode],
    type_map: dict[str, graphql.GraphQLNamedType] | None,
    syntax: _Syntax | None,
    parent: str,
    path: int,
) -> graphql.SelectionSetNode:
    selections: list[graphql.SelectionNode] = [
        _field(node, type_map, syntax, parent, path) for node in nodes if node[1] is None
    ]
    seen: dict[str, graphql.GraphQLType] = {}
    by_type: dict[str, list[SelectionNode]] = {}
    for node in nodes:
        if node[1] is not None:
            by_type.setdefault(node[1], []).append(node)
    for on_type in sorted(by_type):
        assert type_map is not None
        fields = _fields(type_map, on_type)
        fragment_path = zlib.crc32(on_type.encode(), path) if syntax is not None else 0
        frag_fields: list[graphql.SelectionNode] = []
        for node in by_type[on_type]:
            name = node[0]
            field_type = fields[name].type
            alias = None
            if name in seen and not is_equal_type(seen[name], field_type):
                alias = graphql.NameNode(value=_conflict_alias(name, field_type))
            frag_fields.append(_field(node, type_map, syntax, on_type, fragment_path, alias))
            seen.setdefault(name, field_type)
        selection_set = graphql.SelectionSetNode(selections=ast_sequence(frag_fields))
        directives: tuple[graphql.DirectiveNode, ...] = ast_sequence()
        if syntax is not None:
            site = fragment_path % SITES
            directives = syntax.directive(site)
            spread = syntax.hoist(site, on_type, selection_set, directives)
            if spread is not None:
                selections.append(spread)
                continue
        selections.append(
            graphql.InlineFragmentNode(
                type_condition=_named_type(on_type), directives=directives, selection_set=selection_set
            )
        )
    return graphql.SelectionSetNode(selections=ast_sequence(selections))


def build_selection_set(
    nodes: list[SelectionNode], type_map: dict[str, graphql.GraphQLNamedType] | None = None
) -> graphql.SelectionSetNode:
    return _build(nodes, type_map, None, "", 0)


def build_document(
    nodes: list[SelectionNode], kind: graphql.OperationType, type_map: dict[str, graphql.GraphQLNamedType]
) -> graphql.DocumentNode:
    return make_document_node(build_selection_set(nodes, type_map).selections, kind=kind)


class Documents(st.SearchStrategy[graphql.DocumentNode]):
    """Documents for drawn selections; some get aliases, `@skip` / `@include`, a name and named fragments."""

    def __init__(
        self,
        selection: st.SearchStrategy[list[SelectionNode]],
        kind: graphql.OperationType,
        root: str,
        type_map: dict[str, graphql.GraphQLNamedType],
    ) -> None:
        super().__init__()
        self.selection = selection
        self.kind = kind
        self.root = root
        self.type_map = type_map

    def do_draw(self, data: ConjectureData) -> graphql.DocumentNode:
        # Syntax comes first and as primitive draws: a few choices at fixed positions, whatever the selection is
        syntax = _Syntax(data) if data.draw_boolean(SYNTAX) else None
        nodes = data.draw(self.selection)
        if syntax is None:
            return build_document(nodes, self.kind, self.type_map)
        if syntax.aliases:
            _response_keys(nodes, self.type_map, syntax.keys)
        selections = _build(nodes, self.type_map, syntax, self.root, 0).selections
        return make_document_node(selections, kind=self.kind, name=syntax.operation, fragments=syntax.definitions)
