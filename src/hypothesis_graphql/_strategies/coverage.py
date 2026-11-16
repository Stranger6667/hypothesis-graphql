from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Iterator
from typing import cast

import graphql
from hypothesis.errors import InvalidArgument

from .. import nodes
from ..types import SelectionNodes
from . import validation
from .ast import make_mutation, make_query
from .builder import SelectionNode, build_selection_set
from .oracle import is_leaf, unwrap

Arguments = list[graphql.ArgumentNode]
# (field name, type the field returns, required arguments, all buildable arguments)
Usable = tuple[str, graphql.GraphQLNamedType, Arguments, Arguments]
Root = tuple[graphql.GraphQLObjectType, Callable[[SelectionNodes], graphql.DocumentNode]]
SCALARS: dict[str, graphql.ValueNode] = {
    "Int": nodes.Int(0),
    "Float": nodes.Float(0.0),
    "String": nodes.String(""),
    "ID": nodes.String(""),
    "Boolean": nodes.Boolean(False),
}
TYPENAME: list[SelectionNode] = [("__typename", None, [], [])]


def _default(node: graphql.GraphQLArgument | graphql.GraphQLInputField) -> graphql.ValueNode | None:
    return node.ast_node.default_value if node.ast_node is not None else None


def _value(
    type_: graphql.GraphQLInputType, default: graphql.ValueNode | None = None, visiting: frozenset[str] = frozenset()
) -> graphql.ValueNode | None:
    if default is not None:
        return default
    if isinstance(type_, graphql.GraphQLNonNull):
        return _value(type_.of_type, None, visiting)
    if isinstance(type_, graphql.GraphQLList):
        return nodes.List([])
    if isinstance(type_, graphql.GraphQLEnumType):
        return nodes.Enum(next(iter(type_.values)))
    if isinstance(type_, graphql.GraphQLScalarType):
        # Custom scalars have no known literal form
        return SCALARS.get(type_.name)
    if not isinstance(type_, graphql.GraphQLInputObjectType) or type_.name in visiting:
        return None
    visiting |= {type_.name}
    one_of = getattr(type_, "is_one_of", False)
    fields = []
    for name, field in type_.fields.items():
        if one_of or graphql.is_required_input_field(field):
            value = _value(field.type, None, visiting)
            if value is not None:
                fields.append(graphql.ObjectFieldNode(name=graphql.NameNode(value=name), value=value))
                if one_of:
                    break
            elif not one_of:
                return None
    return nodes.Object(fields) if fields or not one_of else None


def _arguments(field: graphql.GraphQLField) -> tuple[Arguments, Arguments] | None:
    required, full = [], []
    for name, argument in field.args.items():
        value = _value(argument.type, _default(argument))
        if value is None:
            if graphql.is_required_argument(argument):
                return None
            continue
        node = graphql.ArgumentNode(name=graphql.NameNode(value=name), value=value)
        full.append(node)
        if graphql.is_required_argument(argument):
            required.append(node)
    return required, full


def _usable_fields(
    schema: graphql.GraphQLSchema, roots: list[Root], fields: tuple[str, ...] | None
) -> dict[str, list[Usable]]:
    root_names = {root.name for root, _ in roots}
    usable: dict[str, list[Usable]] = {}
    for type_name, type_ in schema.type_map.items():
        if isinstance(type_, (graphql.GraphQLObjectType, graphql.GraphQLInterfaceType)):
            usable[type_name] = [
                (name, unwrap(field.type), *arguments)
                for name, field in type_.fields.items()
                if (fields is None or type_name not in root_names or name in fields)
                and (arguments := _arguments(field)) is not None
            ]
    return usable


def _shortest_selections(
    schema: graphql.GraphQLSchema, usable: dict[str, list[Usable]]
) -> dict[str, list[SelectionNode]]:
    # Each round resolves the types one level further from a leaf, so every selection is the shallowest one
    done: dict[str, list[SelectionNode]] = {}
    while True:
        found: dict[str, list[SelectionNode]] = {}
        for type_name, type_ in schema.type_map.items():
            if type_name in done:
                continue
            if isinstance(type_, graphql.GraphQLUnionType):
                for member in type_.types:
                    if member.name in done:
                        found[type_name] = [
                            (name, member.name, children, args) for name, _, children, args in done[member.name]
                        ]
                        break
            for name, target, required, _ in usable.get(type_name, ()):
                if is_leaf(target) or target.name in done:
                    found[type_name] = [(name, None, done.get(target.name, []), required)]
                    break
        if not found:
            return done
        done.update(found)


def _covered(
    schema: graphql.GraphQLSchema, type_name: str, selection: list[SelectionNode]
) -> Iterator[tuple[str, ...]]:
    for name, on_type, children, arguments in selection:
        if name == "__typename":
            continue
        parent = cast("graphql.GraphQLObjectType | graphql.GraphQLInterfaceType", schema.type_map[on_type or type_name])
        yield parent.name, name
        for argument in arguments:
            yield parent.name, name, argument.name.value
        yield from _covered(schema, unwrap(parent.fields[name].type).name, children)


def _generate(
    schema: graphql.GraphQLSchema, roots: list[Root], fields: tuple[str, ...] | None
) -> Iterator[graphql.DocumentNode]:
    usable = _usable_fields(schema, roots, fields)
    shortest = _shortest_selections(schema, usable)
    seen: set[str] = set()
    covered: set[tuple[str, ...]] = set()
    for root, make in roots:
        # Breadth-first, so the spine recorded for a type is a shortest path from the root
        queue: deque[tuple[graphql.GraphQLNamedType, tuple[tuple[str, str | None, Arguments], ...], str | None]]
        queue = deque([(root, (), None)])
        while queue:
            type_, spine, on_type = queue.popleft()
            if type_.name in seen:
                continue
            seen.add(type_.name)
            if isinstance(type_, graphql.GraphQLUnionType):
                queue.extend((member, spine, member.name) for member in type_.types)
            elif isinstance(type_, graphql.GraphQLInterfaceType):
                queue.extend((member, spine, member.name) for member in schema.get_implementations(type_).objects)
            selection: list[SelectionNode] = []
            variants: list[list[SelectionNode]] = []
            for name, target, required, full in usable.get(type_.name, ()):
                children = [] if is_leaf(target) else shortest.get(target.name, TYPENAME)
                selection.append((name, on_type, children, required))
                if len(full) > len(required):
                    variants.append([(name, on_type, children, full)])
                if not is_leaf(target):
                    queue.append((target, (*spine, (name, on_type, required)), None))
            # Mutations have side effects: one root field per document
            groups = [[node] for node in selection] if type_ is schema.mutation_type else [selection] * bool(selection)
            for group in groups + variants:
                for step_name, step_on_type, step_arguments in reversed(spine):
                    group = [(step_name, step_on_type, group, step_arguments)]
                # Selections extended to a leaf already cover parts of other types
                added = set(_covered(schema, root.name, group))
                if added <= covered:
                    continue
                covered |= added
                yield make(build_selection_set(group, schema.type_map).selections)


def covering_operations(
    schema: str | graphql.GraphQLSchema, *, fields: Iterable[str] | None = None
) -> Iterator[graphql.DocumentNode]:
    """Yield a deterministic set of minimal valid operations using every reachable field and argument at least once."""
    parsed = validation.maybe_parse_schema(schema)
    roots: list[Root] = []
    if parsed.query_type is not None:
        roots.append((parsed.query_type, make_query))
    if parsed.mutation_type is not None:
        roots.append((parsed.mutation_type, make_mutation))
    if not roots:
        raise InvalidArgument("Query or Mutation type must be provided")
    if fields is not None:
        fields = tuple(fields)
        validation.validate_fields(fields, [name for root, _ in roots for name in root.fields])
    return _generate(parsed, roots, fields)
