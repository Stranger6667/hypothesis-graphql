"""Set of function for creating GraphQL nodes.

Most of them exist to avoid using lambdas, which might become expensive in Hypothesis in some cases.
"""
from functools import lru_cache
from typing import Callable, List, Optional, Tuple

import graphql

from ..types import SelectionNodes
from .aliases import add_selection_aliases

FieldNodeInput = Tuple[List[graphql.ArgumentNode], Optional[SelectionNodes]]


@lru_cache()
def inline_fragment(type_name: str) -> Callable[[SelectionNodes], graphql.InlineFragmentNode]:
    def factory(nodes: SelectionNodes) -> graphql.InlineFragmentNode:
        return graphql.InlineFragmentNode(
            type_condition=graphql.NamedTypeNode(
                name=graphql.NameNode(value=type_name),
            ),
            selection_set=graphql.SelectionSetNode(kind="selection_set", selections=nodes),
        )

    return factory


@lru_cache()
def argument(name: str) -> Callable[[graphql.ValueNode], graphql.ArgumentNode]:
    def factory(value: graphql.ValueNode) -> graphql.ArgumentNode:
        return graphql.ArgumentNode(name=graphql.NameNode(value=name), value=value)

    return factory


@lru_cache()
def field(name: str) -> Callable[[FieldNodeInput], graphql.FieldNode]:
    def factory(tup: FieldNodeInput) -> graphql.FieldNode:
        return graphql.FieldNode(
            name=graphql.NameNode(value=name),
            arguments=tup[0],
            selection_set=graphql.SelectionSetNode(kind="selection_set", selections=add_selection_aliases(tup[1])),
        )

    return factory


@lru_cache()
def object_field(name: str) -> Callable[[graphql.ValueNode], graphql.ObjectFieldNode]:
    def factory(value: graphql.ValueNode) -> graphql.ObjectFieldNode:
        return graphql.ObjectFieldNode(name=graphql.NameNode(value=name), value=value)

    return factory
