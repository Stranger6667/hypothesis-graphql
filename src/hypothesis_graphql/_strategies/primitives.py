"""Strategies for simple types like scalars or enums."""
from typing import Type, Union

import graphql
from hypothesis import strategies as st

from ..types import ScalarValueNode

MIN_INT = -(2**31)
MAX_INT = 2**31 - 1

TEXT_STRATEGY = st.text(alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=0xFFFF))


def scalar(type_: graphql.GraphQLScalarType, nullable: bool = True) -> st.SearchStrategy[ScalarValueNode]:
    type_name = type_.name
    if type_name == "Int":
        return int_(nullable)
    if type_name == "Float":
        return float_(nullable)
    if type_name == "String":
        return string(nullable)
    if type_name == "ID":
        return id_(nullable)
    if type_name == "Boolean":
        return boolean(nullable)
    raise TypeError("Custom scalar types are not supported")


def enum(type_: graphql.GraphQLEnumType, nullable: bool = True) -> st.SearchStrategy[graphql.EnumValueNode]:
    values = st.sampled_from(list(type_.values))
    return maybe_null(values.map(make_enum_node), nullable)


def int_(nullable: bool = True) -> st.SearchStrategy[graphql.IntValueNode]:
    values = st.integers(min_value=MIN_INT, max_value=MAX_INT)
    return maybe_null(values.map(make_int_node), nullable)


def float_(nullable: bool = True) -> st.SearchStrategy[graphql.FloatValueNode]:
    values = st.floats(allow_infinity=False, allow_nan=False)
    return maybe_null(values.map(make_float_node), nullable)


def string(nullable: bool = True) -> st.SearchStrategy[graphql.StringValueNode]:
    values = st.text(alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=0xFFFF))
    return maybe_null(values.map(make_string_node), nullable)


def id_(nullable: bool = True) -> st.SearchStrategy[Union[graphql.StringValueNode, graphql.IntValueNode]]:
    return string(nullable) | int_(nullable)


def boolean(nullable: bool = True) -> st.SearchStrategy[graphql.BooleanValueNode]:
    return maybe_null(st.booleans().map(make_boolean_node), nullable)


def maybe_null(strategy: st.SearchStrategy, nullable: bool) -> st.SearchStrategy:
    if nullable:
        strategy |= st.just(graphql.NullValueNode())
    return strategy


# Separate functions to use in `map` and avoid costs of handling lambda
# constructors are passed as locals to optimize the byte code a little


def make_boolean_node(
    value: bool, BooleanValueNode: Type[graphql.BooleanValueNode] = graphql.BooleanValueNode
) -> graphql.BooleanValueNode:
    return BooleanValueNode(value=value)


def make_string_node(
    value: str, StringValueNode: Type[graphql.StringValueNode] = graphql.StringValueNode
) -> graphql.StringValueNode:
    return StringValueNode(value=value)


def make_float_node(
    value: float, FloatValueNode: Type[graphql.FloatValueNode] = graphql.FloatValueNode
) -> graphql.FloatValueNode:
    return FloatValueNode(value=str(value))


def make_int_node(value: int, IntValueNode: Type[graphql.IntValueNode] = graphql.IntValueNode) -> graphql.IntValueNode:
    return IntValueNode(value=str(value))


def make_enum_node(
    value: str, EnumValueNode: Type[graphql.EnumValueNode] = graphql.EnumValueNode
) -> graphql.EnumValueNode:
    return EnumValueNode(value=value)
