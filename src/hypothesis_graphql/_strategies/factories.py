"""Set of function for creating GraphQL nodes.

Most of them exist to avoid using lambdas, which might become expensive in Hypothesis in some cases.
"""
from functools import lru_cache
from typing import Callable, List, Optional, Tuple, Type

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


def object_value(fields: List[graphql.ObjectFieldNode]) -> graphql.ObjectValueNode:
    return graphql.ObjectValueNode(fields=fields)


def list_value(values: List[graphql.ValueNode]) -> graphql.ListValueNode:
    return graphql.ListValueNode(values=values)


# Boolean & Enum nodes have a limited set of variants, therefore caching is effective in this case


@lru_cache()
def boolean(value: bool) -> graphql.BooleanValueNode:
    return graphql.BooleanValueNode(value=value)


@lru_cache()
def enum(value: str) -> graphql.EnumValueNode:
    return graphql.EnumValueNode(value=value)


# Other types of nodes are not that cache-efficient.
# Constructors are passed as locals to optimize the byte code a little


def string(
    value: str, StringValueNode: Type[graphql.StringValueNode] = graphql.StringValueNode
) -> graphql.StringValueNode:
    return StringValueNode(value=value)


def float_(
    value: float, FloatValueNode: Type[graphql.FloatValueNode] = graphql.FloatValueNode
) -> graphql.FloatValueNode:
    return FloatValueNode(value=str(value))


def int_(value: int, IntValueNode: Type[graphql.IntValueNode] = graphql.IntValueNode) -> graphql.IntValueNode:
    return IntValueNode(value=str(value))
