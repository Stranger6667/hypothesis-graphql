"""Strategies for simple types like scalars or enums."""
from typing import Union

import graphql
from hypothesis import strategies as st

from ..types import ScalarValueNode


def scalar(type_: graphql.GraphQLScalarType, nullable: bool = True) -> st.SearchStrategy[ScalarValueNode]:
    if type_.name == "Int":
        return int_(nullable)
    if type_.name == "Float":
        return float_(nullable)
    if type_.name == "String":
        return string(nullable)
    if type_.name == "ID":
        return id_(nullable)
    if type_.name == "Boolean":
        return boolean(nullable)
    raise TypeError("Custom scalar types are not supported")


def enum(type_: graphql.GraphQLEnumType, nullable: bool = True) -> st.SearchStrategy[graphql.EnumValueNode]:
    enum_value = st.sampled_from(list(type_.values))
    return _maybe_null(st.builds(graphql.EnumValueNode, value=enum_value), nullable)


def int_(nullable: bool = True) -> st.SearchStrategy[graphql.IntValueNode]:
    value = st.integers().map(str)
    return _maybe_null(st.builds(graphql.IntValueNode, value=value), nullable)


def float_(nullable: bool = True) -> st.SearchStrategy[graphql.FloatValueNode]:
    value = st.floats(allow_infinity=False, allow_nan=False).map(str)
    return _maybe_null(st.builds(graphql.FloatValueNode, value=value), nullable)


def string(nullable: bool = True) -> st.SearchStrategy[graphql.StringValueNode]:
    value = st.text(alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=0xFFFF))
    return _maybe_null(st.builds(graphql.StringValueNode, value=value), nullable)


def id_(nullable: bool = True) -> st.SearchStrategy[Union[graphql.StringValueNode, graphql.IntValueNode]]:
    return string(nullable) | int_(nullable)


def boolean(nullable: bool = True) -> st.SearchStrategy[graphql.BooleanValueNode]:
    return _maybe_null(st.builds(graphql.BooleanValueNode, value=st.booleans()), nullable)


def _maybe_null(strategy: st.SearchStrategy, nullable: bool) -> st.SearchStrategy:
    if nullable:
        strategy |= st.just(graphql.NullValueNode())
    return strategy
