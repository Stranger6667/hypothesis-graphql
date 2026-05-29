from typing import Dict, List, Optional, Sequence, Tuple

import graphql
from graphql import is_equal_type

from .strategy import make_type_name

# (field_name, on_type, children, arguments)
SelectionNode = Tuple[str, Optional[str], "List[SelectionNode]", List[graphql.ArgumentNode]]


def _field_node(
    name: str, children: Sequence[graphql.SelectionNode], args: List[graphql.ArgumentNode]
) -> graphql.FieldNode:
    selection_set = graphql.SelectionSetNode(selections=tuple(children)) if children else None
    return graphql.FieldNode(name=graphql.NameNode(value=name), arguments=tuple(args), selection_set=selection_set)


def build_selection_set(
    nodes: "List[SelectionNode]", type_map: Optional[Dict[str, graphql.GraphQLNamedType]] = None
) -> graphql.SelectionSetNode:
    selections: List[graphql.SelectionNode] = []
    for name, on, children, args in nodes:
        if on is not None:
            continue
        child = list(build_selection_set(children, type_map).selections) if children else []
        selections.append(_field_node(name, child, args))

    seen: Dict[str, graphql.GraphQLType] = {}
    by_type: Dict[str, List[SelectionNode]] = {}
    for node in nodes:
        if node[1] is not None:
            by_type.setdefault(node[1], []).append(node)
    for on_type in sorted(by_type):
        assert type_map is not None
        fragment_type = type_map[on_type]
        frag_fields: List[graphql.SelectionNode] = []
        for name, _on_type, children, args in by_type[on_type]:
            field_type = fragment_type.fields[name].type
            child = list(build_selection_set(children, type_map).selections) if children else []
            field = _field_node(name, child, args)
            if name in seen and not is_equal_type(seen[name], field_type):
                field.alias = graphql.NameNode(value=f"{name}_{make_type_name(field_type)}")
            frag_fields.append(field)
            seen.setdefault(name, field_type)
        selections.append(
            graphql.InlineFragmentNode(
                type_condition=graphql.NamedTypeNode(name=graphql.NameNode(value=on_type)),
                selection_set=graphql.SelectionSetNode(selections=tuple(frag_fields)),
            )
        )
    return graphql.SelectionSetNode(selections=tuple(selections))
