"""Strategies for simple types like scalars or enums."""
from functools import lru_cache
from typing import Tuple, Type, Union

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from .. import nodes
from ..types import ScalarValueNode

MIN_INT = -(2**31)
MAX_INT = 2**31 - 1


# `String` version without extra `str` call
def _string(
    value: str, StringValueNode: Type[graphql.StringValueNode] = graphql.StringValueNode
) -> graphql.StringValueNode:
    return StringValueNode(value=value)


STRING_STRATEGY = st.text(alphabet=st.characters(blacklist_categories=("Cs",), max_codepoint=0xFFFF)).map(_string)
INTEGER_STRATEGY = st.integers(min_value=MIN_INT, max_value=MAX_INT).map(nodes.Int)
FLOAT_STRATEGY = st.floats(allow_infinity=False, allow_nan=False).map(nodes.Float)
BOOLEAN_STRATEGY = st.booleans().map(nodes.Boolean)
NULL_STRATEGY = st.just(nodes.Null)


@lru_cache(maxsize=16)
def scalar(type_name: str, nullable: bool = True) -> st.SearchStrategy[ScalarValueNode]:
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
    raise InvalidArgument(
        f"Scalar {type_name!r} is not supported. "
        "Provide a Hypothesis strategy via the `custom_scalars` argument to generate it."
    )


def int_(nullable: bool = True) -> st.SearchStrategy[graphql.IntValueNode]:
    return maybe_null(INTEGER_STRATEGY, nullable)


def float_(nullable: bool = True) -> st.SearchStrategy[graphql.FloatValueNode]:
    return maybe_null(FLOAT_STRATEGY, nullable)


def string(nullable: bool = True) -> st.SearchStrategy[graphql.StringValueNode]:
    return maybe_null(STRING_STRATEGY, nullable)


def id_(nullable: bool = True) -> st.SearchStrategy[Union[graphql.StringValueNode, graphql.IntValueNode]]:
    return string(nullable) | int_(nullable)


def boolean(nullable: bool = True) -> st.SearchStrategy[graphql.BooleanValueNode]:
    return maybe_null(BOOLEAN_STRATEGY, nullable)


def maybe_null(strategy: st.SearchStrategy, nullable: bool) -> st.SearchStrategy:
    if nullable:
        strategy |= NULL_STRATEGY
    return strategy


@lru_cache(maxsize=64)
def enum(values: Tuple[str], nullable: bool = True) -> st.SearchStrategy[graphql.EnumValueNode]:
    return maybe_null(st.sampled_from(values).map(nodes.Enum), nullable)
