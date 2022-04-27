"""Strategies for simple types like scalars or enums."""
from functools import lru_cache
from typing import Optional, Tuple, Type, TypeVar, Union

import graphql
from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument

from .. import nodes
from ..types import ScalarValueNode

T = TypeVar("T")
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
def scalar(
    type_name: str, nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[ScalarValueNode]:
    if type_name == "Int":
        return int_(nullable, default)
    if type_name == "Float":
        return float_(nullable, default)
    if type_name == "String":
        return string(nullable, default)
    if type_name == "ID":
        return id_(nullable, default)
    if type_name == "Boolean":
        return boolean(nullable, default)
    raise InvalidArgument(
        f"Scalar {type_name!r} is not supported. "
        "Provide a Hypothesis strategy via the `custom_scalars` argument to generate it."
    )


def int_(nullable: bool = True, default: Optional[graphql.ValueNode] = None) -> st.SearchStrategy[graphql.IntValueNode]:
    return maybe_default(maybe_null(INTEGER_STRATEGY, nullable), default=default)


def float_(
    nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.FloatValueNode]:
    return maybe_default(maybe_null(FLOAT_STRATEGY, nullable), default=default)


def string(
    nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.StringValueNode]:
    return maybe_default(
        maybe_null(STRING_STRATEGY, nullable),
        default=default,
    )


def id_(
    nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[Union[graphql.StringValueNode, graphql.IntValueNode]]:
    return maybe_default(string(nullable) | int_(nullable), default=default)


def boolean(
    nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.BooleanValueNode]:
    return maybe_default(maybe_null(BOOLEAN_STRATEGY, nullable), default=default)


def maybe_null(strategy: st.SearchStrategy[T], nullable: bool) -> st.SearchStrategy[T]:
    if nullable:
        strategy |= NULL_STRATEGY
    return strategy


def custom(
    strategy: st.SearchStrategy, nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy:
    return maybe_default(maybe_null(strategy, nullable), default=default)


def maybe_default(
    strategy: st.SearchStrategy[T], *, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[T]:
    if default is not None:
        strategy |= st.just(default)
    return strategy


@lru_cache(maxsize=64)
def enum(
    values: Tuple[str], nullable: bool = True, default: Optional[graphql.ValueNode] = None
) -> st.SearchStrategy[graphql.EnumValueNode]:
    return maybe_default(maybe_null(st.sampled_from(values).map(nodes.Enum), nullable), default=default)


def list_(
    strategy: st.SearchStrategy[graphql.ListValueNode],
    nullable: bool = True,
    default: Optional[graphql.ValueNode] = None,
) -> st.SearchStrategy[graphql.ListValueNode]:
    return maybe_default(maybe_null(strategy.map(nodes.List), nullable), default=default)
