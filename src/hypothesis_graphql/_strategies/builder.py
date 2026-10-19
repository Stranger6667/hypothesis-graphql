from __future__ import annotations

from collections.abc import Sequence

import graphql
from graphql import is_equal_type

from .._compat import ast_sequence
from .strategy import make_type_name

# (field_name, on_type, children, arguments)
SelectionNode = tuple[str, str | None, "list[SelectionNode]", list[graphql.ArgumentNode]]


def _field_node(
    name: str,
    children: Sequence[graphql.SelectionNode],
    args: list[graphql.ArgumentNode],
    alias: graphql.NameNode | None = None,
) -> graphql.FieldNode:
    selection_set = graphql.SelectionSetNode(selections=ast_sequence(children)) if children else None
    return graphql.FieldNode(
        name=graphql.NameNode(value=name), alias=alias, arguments=ast_sequence(args), selection_set=selection_set
    )


def build_selection_set(
    nodes: list[SelectionNode], type_map: dict[str, graphql.GraphQLNamedType] | None = None
) -> graphql.SelectionSetNode:
    selections: list[graphql.SelectionNode] = []
    for name, on, children, args in nodes:
        if on is not None:
            continue
        child = list(build_selection_set(children, type_map).selections) if children else []
        selections.append(_field_node(name, child, args))

    seen: dict[str, graphql.GraphQLType] = {}
    by_type: dict[str, list[SelectionNode]] = {}
    for node in nodes:
        if node[1] is not None:
            by_type.setdefault(node[1], []).append(node)
    for on_type in sorted(by_type):
        assert type_map is not None
        fragment_type = type_map[on_type]
        frag_fields: list[graphql.SelectionNode] = []
        for name, _on_type, children, args in by_type[on_type]:
            field_type = fragment_type.fields[name].type
            child = list(build_selection_set(children, type_map).selections) if children else []
            alias = None
            if name in seen and not is_equal_type(seen[name], field_type):
                alias = graphql.NameNode(value=f"{name}_{make_type_name(field_type)}")
            frag_fields.append(_field_node(name, child, args, alias))
            seen.setdefault(name, field_type)
        selections.append(
            graphql.InlineFragmentNode(
                type_condition=graphql.NamedTypeNode(name=graphql.NameNode(value=on_type)),
                selection_set=graphql.SelectionSetNode(selections=ast_sequence(frag_fields)),
            )
        )
    return graphql.SelectionSetNode(selections=ast_sequence(selections))
