import typing
from functools import lru_cache

import graphql

# These types are not cache-efficient.
# Constructors are passed as locals to optimize the byte code a little


def String(
    value: typing.Any, StringValueNode: typing.Type[graphql.StringValueNode] = graphql.StringValueNode
) -> graphql.StringValueNode:
    return StringValueNode(value=str(value))


def Float(
    value: float, FloatValueNode: typing.Type[graphql.FloatValueNode] = graphql.FloatValueNode
) -> graphql.FloatValueNode:
    return FloatValueNode(value=str(value))


def Int(value: int, IntValueNode: typing.Type[graphql.IntValueNode] = graphql.IntValueNode) -> graphql.IntValueNode:
    return IntValueNode(value=str(value))


def Object(
    fields: typing.List[graphql.ObjectFieldNode],
    ObjectValueNode: typing.Type[graphql.ObjectValueNode] = graphql.ObjectValueNode,
) -> graphql.ObjectValueNode:
    return ObjectValueNode(fields=fields)


def List(
    values: typing.List[graphql.ValueNode], ListValueNode: typing.Type[graphql.ListValueNode] = graphql.ListValueNode
) -> graphql.ListValueNode:
    return ListValueNode(values=values)


# Boolean & Enum nodes have a limited set of variants, therefore caching is effective in this case


@lru_cache()
def Boolean(value: bool) -> graphql.BooleanValueNode:
    return graphql.BooleanValueNode(value=value)


@lru_cache()
def Enum(value: str) -> graphql.EnumValueNode:
    return graphql.EnumValueNode(value=value)


Null = graphql.NullValueNode()
